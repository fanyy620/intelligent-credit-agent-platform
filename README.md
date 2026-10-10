# 智能信贷营销与咨询一体化 Agent 平台

面向商业银行对公信贷场景的全栈 Agent 系统：**Python 智能层**（LangGraph 编排 · 八层提示词体系 · Multi-Agent 双视角辩论）+ **SSM 经典业务层**（Spring + SpringMVC + MyBatis + Redis）+ **Vue 前端**（南洋商业银行风格 · 全站悬浮窗 Copilot）。

> 机制设计 > 模型能力 —— 本系统的 Multi-Agent 辩论、PIT 数据时点约束、推荐经验库等设计迁移自中金研报《大模型系列(6)：Multi-Agent 如何辩论出基本面 Alpha？》，对照表见 `credit-agent-platform/docs/cicc-methodology-mapping.md`。

## 仓库结构

```
├── credit-agent-platform/     # Agent 智能层（Python，纯标准库可离线演示）
│   ├── src/                   #   agent / intent / memory / recommend / debate
│   │                          #   compliance / mcp_server / observability / llm
│   ├── data/                  #   1000 条意图训练数据 + 生成脚本
│   ├── training/              #   LLaMA-Factory LoRA 意图路由微调配置
│   ├── docs/                  #   实现路径指南 · 提示词设计 · 中金方法论对照 · 真实案例报告
│   └── tests/                 #   95 个离线测试全绿
│
└── credit-agent-web/          # 业务系统层（前后端分离）
    ├── backend/               #   SSM（Spring 5.3 XML 配置版）+ MyBatis + MySQL + Redis，Maven WAR
    ├── frontend/              #   Vue 2 + Element UI + Vite，悬浮窗语义操作
    ├── mock-backend/          #   内存版演示后端（无 JDK/MySQL 时一键演示）
    └── docs/                  #   部署手册 · NCB 风格参考 · 3 分钟演示脚本
```

## 核心能力

- **三层推荐架构**：槽位抽取（规则+LLM 双通道）→ 规则+RAG 召回 → 四维业务评分 + LLM 重排
- **Multi-Agent 双视角辩论**：风险合规 × 业务增长视角评审推荐结论，硬伤检测触发备选再评估
- **八层提示词体系**：意图 / 槽位 / 回复 / 文案 / 合规 / 重写 / 站点动作 / 辩论，全部输出契约化
- **双重风控文案**：正则 + 语义双闸；模板 + 数据后填充，从机制上杜绝数值幻觉
- **分层记忆**：Redis 短期会话 + PGVector 长期事实 + 推荐经验库（相似案例检索注入）
- **悬浮窗 Copilot**：模糊语义 → 白名单动作（查客户 / 看数据 / 推荐 / 写文案），三道安全闸
- **全链路可观测与降级**：Langfuse 埋点；无 LLM / 无数据库时全链路优雅降级可离线演示

## 快速开始

```bash
# 1. Agent 层（Python 3.10+，无第三方依赖可直接跑 demo）
cd credit-agent-platform
python src/demo.py                 # 离线教学演示
python -m pytest tests/ -q         # 95 个测试

# 2. 全栈演示模式（无需 JDK/MySQL/Redis，一条命令拉起前端+模拟后端+Agent）
cd credit-agent-web/frontend
npm install && npm run dev         # 浏览器打开提示的地址，admin / 123456

# 3. 生产形态：见 credit-agent-web/docs/deployment-guide.md（Tomcat war / MySQL / Redis / nginx）
```

配置真实大模型：复制 `credit-agent-platform/.env.example` 为 `.env`，填入 `DEEPSEEK_API_KEY` 或 `KIMI_API_KEY` 即可从 Mock 切换到真实模型（provider 自动探测链）。

## 文档索引

| 文档 | 内容 |
|---|---|
| `credit-agent-platform/docs/implementation-guide.md` | 重点实现路径（架构 / 调优 / 踩坑实录） |
| `credit-agent-platform/docs/prompt-design.md` | 八层提示词设计与合规策略差异 |
| `credit-agent-platform/docs/cicc-methodology-mapping.md` | 中金 Multi-Agent 方法论 → 本系统对照 |
| `credit-agent-platform/docs/case-study-report.pdf` | 真实案例推理过程报告（逐层留证） |
| `credit-agent-web/docs/deployment-guide.md` | 生产部署手册 |
| `credit-agent-web/docs/demo-script-3min.md` | 3 分钟演示脚本 |

## License

[MIT](LICENSE)
