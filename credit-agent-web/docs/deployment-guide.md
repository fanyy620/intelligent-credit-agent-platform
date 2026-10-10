# 生产部署指南（credit-agent-web）

经典三端部署流程：MySQL/Redis 准备 → Python Agent 常驻 → SSM 打 war 部署 Tomcat →
前端 build 静态资源挂 nginx。全程以 Linux(CentOS/Ubuntu) 为例，Windows 同理。

## 1. 依赖安装要点

### 1.1 MySQL 8

```bash
# Ubuntu
sudo apt install mysql-server
sudo systemctl enable --now mysqld   # 或 mysql

# 初始化库表与种子数据
mysql -uroot -p < backend/sql/init.sql

# 建议创建专用账号（不要用 root 上线）
mysql -uroot -p -e "
CREATE USER 'credit'@'%' IDENTIFIED BY '强密码';
GRANT ALL PRIVILEGES ON credit_web.* TO 'credit'@'%';
FLUSH PRIVILEGES;"
```

### 1.2 Redis

```bash
sudo apt install redis-server
sudo systemctl enable --now redis
# 生产建议开启密码：/etc/redis/redis.conf → requirepass 你的密码
```

### 1.3 JDK 8+ 与 Tomcat 9

- Spring 5.3 是 `javax.*` 体系，**必须部署 Tomcat 9.x**（Tomcat 10 为 `jakarta.*`，不兼容）；
- JDK 8/11/17 均可（pom 编译级别 1.8）。

### 1.4 Python 3.10+

Agent 引擎（`credit-agent-platform`）核心链路零第三方依赖；
如需真实 LLM/PG/Redis 后端，再按 `requirements.txt` 安装并配置 `.env`。

## 2. 配置修改（只改一个文件）

`backend/src/main/resources/jdbc.properties`：

```properties
jdbc.url=jdbc:mysql://生产MySQL地址:3306/credit_web?useUnicode=true&characterEncoding=utf8&serverTimezone=Asia/Shanghai&useSSL=false&allowPublicKeyRetrieval=true
jdbc.username=credit
jdbc.password=强密码
redis.host=生产Redis地址
redis.password=Redis密码
agent.base-url=http://Agent服务器内网地址:8000
jwt.secret=换成足够长的随机串（>=32字节）
```

## 3. Python Agent 常驻（systemd）

```ini
# /etc/systemd/system/credit-agent.service
[Unit]
Description=Credit Agent HTTP Service
After=network.target

[Service]
WorkingDirectory=/opt/credit-agent-platform
ExecStart=/usr/bin/python3 src/api_server.py --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now credit-agent
curl http://127.0.0.1:8000/health   # 验证 status=up
```

## 4. SSM 后端打 war 部署 Tomcat

```bash
cd backend
mvn clean package -DskipTests
# 产物：target/credit-web.war

# 部署：拷贝到 Tomcat webapps 下，上下文即 /credit-web
cp target/credit-web.war /opt/tomcat9/webapps/
/opt/tomcat9/bin/startup.sh

# 验证
curl http://127.0.0.1:8080/credit-web/health
# 登录冒烟
curl -X POST http://127.0.0.1:8080/credit-web/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"123456"}'
```

开发期可用 `mvn tomcat7:run` 内嵌启动（仅限开发，生产勿用内嵌插件）。

## 5. 前端构建与 nginx 部署

```bash
cd frontend
npm install
npm run build          # 产物 dist/
sudo cp -r dist/* /usr/share/nginx/html/credit-web/
```

```nginx
# /etc/nginx/conf.d/credit-web.conf
server {
    listen 80;
    server_name credit.example.com;
    root /usr/share/nginx/html/credit-web;
    index index.html;

    # 前端静态资源（hash 路由无需 try_files 特殊处理）
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 反向代理到 SSM 后端
    location /api/ {
        proxy_pass http://127.0.0.1:8080/credit-web/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 30s;
    }
}
```

> 生产 CORS 收敛：后端 `CorsFilter` 当前放开 `*`，上生产前把
> `Access-Control-Allow-Origin` 改为前端实际域名（同源部署经 nginx 代理后可完全不跨域）。

## 6. 启动顺序与验证清单

```
1. MySQL     → 2. Redis → 3. Python Agent(:8000)
→ 4. Tomcat(:8080/credit-web) → 5. nginx(:80)
```

| 检查项 | 命令/页面 | 预期 |
|--------|-----------|------|
| Agent 健康 | `curl :8000/health` | `status=up` |
| 后端健康 | `curl :8080/credit-web/health` | `web=up`，agent 视情况 |
| 登录 | 页面或 curl `/auth/login` | 返回 token |
| 看板 | 登录后首页 | 统计卡片、意图分布 |
| 智能助理 | 发送“借20万装修推荐一下” | 右侧出现四维评分卡 |
| 降级验证 | 停掉 Agent 再发消息 | 友好提示，其他功能正常 |

## 7. 常见问题

- **Tomcat 10 部署白屏/404 一堆**：Spring 5.3 不兼容 jakarta，换 Tomcat 9；
- **登录立即 401**：Redis 未启动或密码错误，令牌写入失败 → 检查 `redis.*` 配置；
- **看板 Agent 离线**：`agent.base-url` 指向错误，或 Agent 未常驻；
- **中文乱码**：确认 `web.xml` 的 `CharacterEncodingFilter` 在所有过滤器最前，
  Tomcat `server.xml` 的 Connector 加 `URIEncoding="UTF-8"`；
- **时区时间不对**：`jdbc.url` 中 `serverTimezone=Asia/Shanghai` 已配置，
  MySQL 服务器本身时区也需一致。
