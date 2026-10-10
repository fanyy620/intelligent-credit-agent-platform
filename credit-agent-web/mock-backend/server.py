#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
credit-agent-web 演示模式 Mock 后端（纯 Python 标准库，无需 JDK / MySQL / Redis）。

用途：在没有 Java 环境 / 数据库的机器上，一键跑通前端全部页面：
  - 完整实现 SSM 后端（credit-agent-web/backend）的 22 个 REST 端点，
    响应体统一 {code, message, data}，code=0 成功、401 未登录（HTTP 恒为 200，
    与 Java TokenInterceptor 行为一致，前端 axios 拦截器无感切换）；
  - 客户 / 产品 / 会话 / 消息 / 推荐记录 / 文案记录全部保存在内存中，
    种子数据与 backend/sql/init.sql 对齐（同账号、同客户、同 8 个产品）；
  - /chat/send 与 /copy/generate 桥接到真实 Python Agent（默认 127.0.0.1:8000），
    Agent 不可达时按 Java AgentClient 同样的纪律降级（友好提示，不抛异常）；
  - 路由前剥离 /credit-web 上下文前缀：前端 vite 代理 target 为
    http://localhost:8080/credit-web（与真 Tomcat war 包上下文一致），
    因此前端在「mock 模式」与「真 SSM 模式」之间零改动切换。

用法：
  python server.py                     # 监听 [::]:8080（双栈，兼容 localhost→::1 的解析）
  python server.py --host 0.0.0.0 --port 8080 --agent http://127.0.0.1:8000

演示账号：admin / 123456（管理员）、manager01 / 123456（客户经理）。
"""
import argparse
import hashlib
import json
import re
import socket
import sys
import threading
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import request as urlrequest
from urllib.parse import urlparse, parse_qs

# Windows 控制台默认 GBK，中文日志直接打印会 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

CONTEXT_PREFIX = "/credit-web"
LOCK = threading.Lock()

# ------------------------------------------------------------------ 小工具


def now_iso() -> str:
    """前端统一用 new Date(t) 解析，ISO 字符串可读性更好。"""
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def today_prefix() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def next_id(rows: list) -> int:
    return max((int(r.get("id") or 0) for r in rows), default=0) + 1


# ------------------------------------------------------------------ 种子数据
# 与 backend/sql/init.sql 对齐：密码 = MD5(盐 + 明文)，明文均为 123456

ROLES = [
    {"id": 1, "roleKey": "admin", "roleName": "系统管理员", "remark": "全部功能权限"},
    {"id": 2, "roleKey": "manager", "roleName": "客户经理", "remark": "客户管理/智能助理/营销文案"},
]

USERS = [
    {"id": 1, "username": "admin", "password": "5e0ab52f58cad58a4bf59569bfca4e70",
     "salt": "a1b2c3", "nickname": "系统管理员", "roleId": 1, "status": 1,
     "roleKey": "admin", "roleName": "系统管理员"},
    {"id": 2, "username": "manager01", "password": "19bf45eaed94d788c75d2bdc26aba7fc",
     "salt": "d4e5f6", "nickname": "王客户经理", "roleId": 2, "status": 1,
     "roleKey": "manager", "roleName": "客户经理"},
]

# 对公（ToB）演示客户：gender 字段复用为「企业性质」，age 为「成立年限」，
# occupation 为「所属行业」，monthlyIncome 为「月均营收（元）」
CUSTOMERS = [
    {"id": 1, "name": "华创精密制造有限公司", "gender": "民企", "phone": "0755-26881001", "age": 12,
     "occupation": "制造业", "monthlyIncome": 8000000, "creditStatus": "良好",
     "remark": "主营精密零部件，有200万流动资金贷款需求", "createBy": "manager01"},
    {"id": 2, "name": "恒信贸易(深圳)有限公司", "gender": "民企", "phone": "0755-83232002", "age": 8,
     "occupation": "贸易物流", "monthlyIncome": 5000000, "creditStatus": "良好",
     "remark": "进出口贸易，旺季备货融资需求", "createBy": "manager01"},
    {"id": 3, "name": "南天物流集团有限公司", "gender": "国企", "phone": "020-38990003", "age": 15,
     "occupation": "贸易物流", "monthlyIncome": 20000000, "creditStatus": "良好",
     "remark": "区域物流龙头，车队扩张融资", "createBy": "manager01"},
    {"id": 4, "name": "启明生物科技有限公司", "gender": "民企", "phone": "0755-26504004", "age": 5,
     "occupation": "医药科技", "monthlyIncome": 3000000, "creditStatus": "良好",
     "remark": "高新技术企业，研发投入占比高", "createBy": "manager01"},
    {"id": 5, "name": "宏基建筑工程有限公司", "gender": "民企", "phone": "0755-28995005", "age": 20,
     "occupation": "建筑工程", "monthlyIncome": 15000000, "creditStatus": "一般",
     "remark": "项目垫资压力较大，关注供应链融资", "createBy": "admin"},
    {"id": 6, "name": "悦达餐饮管理有限公司", "gender": "小微", "phone": "0755-26666006", "age": 4,
     "occupation": "餐饮服务", "monthlyIncome": 900000, "creditStatus": "有逾期",
     "remark": "连锁门店，两年前有贷款逾期记录", "createBy": "manager01"},
]

# 与 credit-agent-platform/configs/products.yaml 同步（camelCase 为 Java 序列化风格）
PRODUCTS = [
    {"id": 1, "productCode": "xinxiangdai", "name": "信享贷", "category": "消费贷",
     "minAmount": 10000, "maxAmount": 300000, "minTermMonths": 6, "maxTermMonths": 36,
     "annualRateMin": 0.048, "annualRateMax": 0.096, "approvalHours": 2,
     "minAge": 22, "maxAge": 55, "minMonthlyIncome": 4000, "minCreditScore": 600,
     "allowedPurposes": "消费,装修,教育,旅游,医疗", "tags": "纯信用,线上申请,白领,免抵押",
     "description": "面向优质工薪白领的纯信用消费贷款，线上申请免抵押，适合装修教育旅游医疗等大额消费场景",
     "status": 1},
    {"id": 2, "productCode": "xinyidai", "name": "薪易贷", "category": "消费贷",
     "minAmount": 5000, "maxAmount": 200000, "minTermMonths": 3, "maxTermMonths": 24,
     "annualRateMin": 0.054, "annualRateMax": 0.108, "approvalHours": 1,
     "minAge": 20, "maxAge": 50, "minMonthlyIncome": 3000, "minCreditScore": 550,
     "allowedPurposes": "消费,旅游,教育,医疗,周转", "tags": "工薪,代发工资,快速到账",
     "description": "面向代发工资客群的短期小额消费信贷，凭打卡工资即可申请，最快一小时放款",
     "status": 1},
    {"id": 3, "productCode": "jisuxinyongdai", "name": "极速信用贷", "category": "消费贷",
     "minAmount": 1000, "maxAmount": 50000, "minTermMonths": 3, "maxTermMonths": 12,
     "annualRateMin": 0.072, "annualRateMax": 0.144, "approvalHours": 0.5,
     "minAge": 20, "maxAge": 55, "minMonthlyIncome": 2000, "minCreditScore": 520,
     "allowedPurposes": "消费,周转", "tags": "小额,极速,纯线上,门槛最低",
     "description": "小额短期应急信用贷款，全线上自动审批最快三十分钟出结果，门槛低但利率偏高",
     "status": 1},
    {"id": 4, "productCode": "xuezizhuxuedai", "name": "学子助学贷", "category": "消费贷",
     "minAmount": 5000, "maxAmount": 80000, "minTermMonths": 12, "maxTermMonths": 60,
     "annualRateMin": 0.036, "annualRateMax": 0.049, "approvalHours": 24,
     "minAge": 18, "maxAge": 30, "minMonthlyIncome": 0, "minCreditScore": 500,
     "allowedPurposes": "教育,留学", "tags": "学生,教育分期,低息",
     "description": "面向在校学生及留学群体的低息教育专项贷款，支持学费分期与生活费补助",
     "status": 1},
    {"id": 5, "productCode": "xingyejingyingdai", "name": "兴业经营贷", "category": "经营贷",
     "minAmount": 50000, "maxAmount": 1000000, "minTermMonths": 6, "maxTermMonths": 60,
     "annualRateMin": 0.0435, "annualRateMax": 0.085, "approvalHours": 24,
     "minAge": 22, "maxAge": 60, "minMonthlyIncome": 0, "minCreditScore": 550,
     "allowedPurposes": "经营,周转,进货", "tags": "个体户,小微企业主,营业执照,流水",
     "description": "面向个体工商户与小微企业主的经营性贷款，凭营业执照与经营流水申请，用于进货与资金周转",
     "status": 1},
    {"id": 6, "productCode": "shuiyidai", "name": "税易贷", "category": "经营贷",
     "minAmount": 100000, "maxAmount": 3000000, "minTermMonths": 6, "maxTermMonths": 36,
     "annualRateMin": 0.0385, "annualRateMax": 0.065, "approvalHours": 48,
     "minAge": 23, "maxAge": 60, "minMonthlyIncome": 0, "minCreditScore": 600,
     "allowedPurposes": "经营,周转", "tags": "纳税记录,小微,纯信用,对公",
     "description": "依据企业纳税信用记录授信的小微企业纯信用经营贷，纳税等级越高利率越低",
     "status": 1},
    {"id": 7, "productCode": "anjufangdidai", "name": "安居房抵贷", "category": "房抵贷",
     "minAmount": 200000, "maxAmount": 5000000, "minTermMonths": 12, "maxTermMonths": 120,
     "annualRateMin": 0.0365, "annualRateMax": 0.058, "approvalHours": 72,
     "minAge": 25, "maxAge": 60, "minMonthlyIncome": 8000, "minCreditScore": 580,
     "allowedPurposes": "经营,装修,消费", "tags": "房产抵押,大额,长期,低利率",
     "description": "以住宅房产抵押的大额长期贷款，额度高利率低，适合大额装修经营投入等场景，审批需三到五个工作日",
     "status": 1},
    {"id": 8, "productCode": "cheyidai", "name": "车易贷", "category": "车贷",
     "minAmount": 30000, "maxAmount": 500000, "minTermMonths": 12, "maxTermMonths": 60,
     "annualRateMin": 0.045, "annualRateMax": 0.079, "approvalHours": 4,
     "minAge": 21, "maxAge": 55, "minMonthlyIncome": 5000, "minCreditScore": 560,
     "allowedPurposes": "购车,买车", "tags": "新车,二手车,按揭,经销商合作",
     "description": "面向个人购车场景的汽车按揭贷款，支持新车与二手车，合作经销商可现场办理当天提车",
     "status": 1},
]

# token -> userInfo（等价于 Java 侧 Redis 键 web:token:{jti}）
TOKENS = {}

# 会话 / 消息 / 推荐记录 / 文案记录（seed() 在启动时填充，时间戳=启动时刻，
# 保证数据看板的「今日」统计非零）
SESSIONS = []
MESSAGES = []
RECOMMENDS = []
COPIES = []


def seed() -> None:
    """写入 1 条演示会话（4 条消息、含意图）、1 条推荐记录、2 条文案记录（1 合规 1 违规）。"""
    now = now_iso()
    for c in CUSTOMERS:
        c.setdefault("createTime", now)
        c.setdefault("updateTime", now)
    for p in PRODUCTS:
        p.setdefault("createTime", now)
        p.setdefault("updateTime", now)

    first_msg = "我们是制造业企业，需要200万流动资金贷款用于采购原材料，期限12个月，请帮我推荐合适的信贷产品"
    session = {
        "id": 1,
        "sessionNo": "S" + uuid.uuid4().hex[:16],
        "userId": 2,
        "customerId": 1,
        "title": (first_msg[:20] + "…") if len(first_msg) > 20 else first_msg,
        "createTime": now,
        "updateTime": now,
    }
    SESSIONS.append(session)

    reply = ("根据贵司需求（200 万元流动资金贷款、12 个月期限、原材料采购用途），"
             "为您推荐以下产品：\n"
             "1. 税易贷：年化利率 3.85%-6.50%（单利），6-36 个月，最快 48 小时审批\n"
             "   推荐理由：额度区间 100-300 万完整覆盖需求，凭纳税信用纯信用授信\n"
             "2. 兴业经营贷：年化利率 4.35%-8.50%（单利），6-60 个月，最快 24 小时审批\n"
             "   推荐理由：期限灵活、审批快，但额度上限 100 万需组合融资\n"
             "3. 安居房抵贷：年化利率 3.65%-5.80%（单利），12-120 个月\n"
             "   推荐理由：如有房产可抵押则利率最低，审批需 3-5 个工作日\n"
             "以上额度和利率均以最终审批为准。")
    MESSAGES.extend([
        {"id": 1, "sessionId": 1, "role": "user", "content": first_msg,
         "intent": "", "intentZh": "", "createTime": now},
        {"id": 2, "sessionId": 1, "role": "assistant", "content": reply,
         "intent": "CREDIT_RECOMMEND", "intentZh": "授信推荐", "createTime": now},
        {"id": 3, "sessionId": 1, "role": "user", "content": "税易贷的利率是多少？",
         "intent": "", "intentZh": "", "createTime": now},
        {"id": 4, "sessionId": 1, "role": "assistant",
         "content": "税易贷的年化利率为 3.85%-6.50%（单利），纳税信用等级越高利率越低，具体以审批结果为准。",
         "intent": "PRODUCT_CONSULT", "intentZh": "产品咨询", "createTime": now},
    ])

    def _rec(pid, name, category, rate_range, max_amount, hours,
             amount_s, rate_s, term_s, speed_s, biz_s, sem_s, final_s, reason):
        return {
            "product": {"id": pid, "name": name, "category": category,
                        "rate_range_pct": rate_range, "max_amount": max_amount,
                        "approval_hours": hours},
            "scores": {"amount_score": amount_s, "rate_score": rate_s,
                       "term_score": term_s, "speed_score": speed_s,
                       "business_score": biz_s, "semantic_score": sem_s,
                       "final_score": final_s},
            "reason": reason,
        }

    result_payload = {
        "slots": {"amount": 2000000, "term_months": 12,
                  "purpose": "经营周转", "industry": "制造业"},
        "recommendations": [
            _rec("shuiyidai", "税易贷", "经营贷", "3.85%-6.50%", 3000000, 48,
                 1.0, 0.93, 1.0, 0.62, 0.94, 0.90, 0.918,
                 "额度 100-300 万完整覆盖流动资金需求，纯信用免抵押"),
            _rec("xingyejingyingdai", "兴业经营贷", "经营贷", "4.35%-8.50%", 1000000, 24,
                 0.5, 0.78, 1.0, 0.85, 0.80, 0.84, 0.762,
                 "审批快、期限灵活，但额度上限 100 万需组合融资"),
            _rec("anjufangdidai", "安居房抵贷", "房抵贷", "3.65%-5.80%", 5000000, 72,
                 1.0, 0.97, 1.0, 0.30, 0.81, 0.68, 0.758,
                 "利率最低、额度充足，需房产抵押且审批 3-5 个工作日"),
        ],
    }
    RECOMMENDS.append({
        "id": 1, "sessionId": 1, "customerId": 1, "userId": 2,
        "message": first_msg, "topProduct": "税易贷",
        "resultJson": json.dumps(result_payload, ensure_ascii=False),
        "createTime": now,
    })

    good_template = ("【{product_name}】凭纳税信用，贷动经营未来！授信额度{min_amount}-{max_amount}元，"
                     "年化利率{annual_rate_min}%-{annual_rate_max}%（单利），最快{approval_hours}小时审批。"
                     "纯信用、免抵押、线上申请。贷款有风险，借款需谨慎；具体以实际审批结果为准。")
    good_content = ("【税易贷】凭纳税信用，贷动经营未来！授信额度1000000-3000000元，"
                    "年化利率3.85%-6.50%（单利），最快48小时审批。"
                    "纯信用、免抵押、线上申请。贷款有风险，借款需谨慎；具体以实际审批结果为准。")
    bad_content = ("【兴业经营贷】内部渠道包下款！无视征信、百分百放款，"
                   "保本保息，额度想贷多少贷多少，当天到账！")
    COPIES.extend([
        {"id": 1, "userId": 1, "customerId": None, "productId": "shuiyidai",
         "productName": "税易贷", "channel": "朋友圈",
         "template": good_template, "content": good_content,
         "compliant": 1, "hitRules": "[]",
         "conclusion": "双重风控（正则+语义）审核通过", "createTime": now},
        {"id": 2, "userId": 2, "customerId": 3, "productId": "xingyejingyingdai",
         "productName": "兴业经营贷", "channel": "短信",
         "template": "（人工改写版本，未经模板填充机制）", "content": bad_content,
         "compliant": 0,
         "hitRules": json.dumps(["承诺保本保息", "承诺百分百下款", "无视征信"], ensure_ascii=False),
         "conclusion": "命中 3 条违规规则，建议修改后重新生成", "createTime": now},
    ])


# ------------------------------------------------------------------ Agent 桥接


class AgentBridge:
    """调用真实 Python Agent（api_server.py）。纪律同 Java AgentClient：
    对话失败降级为友好回复，文案失败由上层返回业务错误，绝不向上抛异常。"""

    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def _post(self, path: str, body: dict, timeout: float) -> dict:
        req = urlrequest.Request(
            self.base + path,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("code") != 0:
            raise RuntimeError("Agent 业务错误: %s" % (payload.get("message") if isinstance(payload, dict) else payload))
        data = payload.get("data")
        return data if isinstance(data, dict) else {"data": data}

    def health(self) -> bool:
        try:
            with urlrequest.urlopen(self.base + "/health", timeout=1.5) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            return isinstance(payload, dict) and payload.get("code") == 0
        except Exception:
            return False

    def chat(self, session_no: str, user_id: str, message: str, context: dict | None = None) -> dict:
        body = {"session_id": session_no, "user_id": user_id, "message": message}
        # Copilot 模式：透传前端页面上下文，Agent 据此抽取网站动作（actions）
        if isinstance(context, dict) and context:
            body["context"] = context
        try:
            # 真实 LLM 单轮约 90-130s（kimi-for-coding reasoning 模型），桥接超时给足 180s
            data = self._post("/v1/chat", body, timeout=180)
            data["available"] = True
            return data
        except Exception as e:
            print("[mock-backend] Agent 对话不可用，已降级: %s: %s" % (type(e).__name__, e),
                  file=sys.stderr)
            return {
                "available": False,
                "reply": "智能顾问暂时不可用，请稍后再试。您可先使用企业客户、信贷产品等功能。",
                "error": type(e).__name__,
            }

    def generate_copy(self, user_id: str, product_id: str, channel: str):
        """成功返回 data dict；失败返回 None（上层转换为业务错误提示）。"""
        body = {"user_id": user_id, "product_id": product_id, "channel": channel}
        try:
            data = self._post("/v1/copy/generate", body, timeout=180)
            data["available"] = True
            return data
        except Exception as e:
            print("[mock-backend] Agent 文案不可用: %s: %s" % (type(e).__name__, e),
                  file=sys.stderr)
            return None


# ------------------------------------------------------------------ HTTP 层


class MockHandler(BaseHTTPRequestHandler):
    """统一 {code, message, data} 响应；HTTP 恒 200（与 Java 侧一致），
    业务状态完全由 body.code 表达，前端 axios 拦截器无感处理。"""

    server_version = "CreditWebMock/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: A003
        sys.stderr.write("[mock-backend] %s - %s\n" % (self.address_string(), fmt % args))

    # ---- 基础设施 ----

    @property
    def agent(self) -> AgentBridge:
        return self.server.agent_bridge  # type: ignore[attr-defined]

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, token")
        self.end_headers()
        self.wfile.write(body)

    def _ok(self, data, message: str = "ok") -> None:
        self._send_json({"code": 0, "message": message, "data": data})

    def _fail(self, code: int, message: str) -> None:
        self._send_json({"code": code, "message": message, "data": None})

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("请求体不是合法 JSON")
        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象")
        return data

    def _query(self) -> dict:
        qs = parse_qs(urlparse(self.path).query)
        return {k: v[0] for k, v in qs.items()}

    def _int_param(self, query: dict, name: str, default: int, lo: int, hi: int) -> int:
        try:
            return min(max(int(query.get(name, default)), lo), hi)
        except (TypeError, ValueError):
            return default

    def _current_user(self):
        """从 Authorization: Bearer / token 头解析登录态；返回 (userInfo, reason)。"""
        auth = self.headers.get("Authorization")
        token = None
        if auth and auth.startswith("Bearer "):
            token = auth[7:].strip()
        elif self.headers.get("token"):
            token = self.headers.get("token").strip()
        if not token:
            return None, "未登录或缺少令牌"
        info = TOKENS.get(token)
        if info is None:
            return None, "令牌无效或已过期，请重新登录"
        return info, None

    # ---- 方法入口 ----

    def do_OPTIONS(self):  # noqa: N802
        self._send_json({"code": 0, "message": "ok", "data": None})

    def do_GET(self):  # noqa: N802
        self._dispatch("GET")

    def do_POST(self):  # noqa: N802
        self._dispatch("POST")

    def do_PUT(self):  # noqa: N802
        self._dispatch("PUT")

    def do_DELETE(self):  # noqa: N802
        self._dispatch("DELETE")

    # ---- 路由 ----

    def _path(self) -> str:
        path = urlparse(self.path).path
        if path.startswith(CONTEXT_PREFIX):
            path = path[len(CONTEXT_PREFIX):] or "/"
        if len(path) > 1:
            path = path.rstrip("/")
        return path

    def _dispatch(self, method: str) -> None:
        path = self._path()
        try:
            # 公开端点（对应 spring-mvc.xml 的 mvc:exclude-mapping）
            if method == "POST" and path == "/auth/login":
                body = self._read_body()
                return self._login(body)
            if method == "GET" and path == "/health":
                return self._ok({
                    "status": "up",
                    "service": "credit-web-mock",
                    "mode": "demo",
                    "agentAvailable": self.agent.health(),
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                })

            # 其余端点一律要求登录态
            user, reason = self._current_user()
            if user is None:
                return self._fail(401, reason)

            body = self._read_body() if method in ("POST", "PUT") else {}
            query = self._query()

            # 认证
            if method == "POST" and path == "/auth/logout":
                return self._logout()
            if method == "GET" and path == "/auth/info":
                return self._ok(user)

            # 数据看板
            if method == "GET" and path == "/dashboard/stats":
                return self._dashboard_stats()

            # 客户管理
            if method == "GET" and path == "/customer/page":
                return self._customer_page(query)
            if method == "POST" and path == "/customer":
                return self._customer_create(body, user)
            m = self._match(r"^/customer/(\d+)$", path)
            if m and method == "GET":
                return self._customer_detail(int(m.group(1)))
            if m and method == "PUT":
                return self._customer_update(int(m.group(1)), body)
            if m and method == "DELETE":
                return self._customer_delete(int(m.group(1)))

            # 产品管理
            if method == "GET" and path == "/product/list":
                return self._ok([p for p in PRODUCTS if p.get("status") == 1])
            if method == "POST" and path == "/product":
                return self._product_create(body, user)
            m = self._match(r"^/product/(\d+)$", path)
            if m and method == "PUT":
                return self._product_update(int(m.group(1)), body, user)
            if m and method == "DELETE":
                return self._product_delete(int(m.group(1)), user)

            # 智能对话
            if method == "POST" and path == "/chat/send":
                return self._chat_send(body, user)
            if method == "GET" and path == "/chat/sessions":
                return self._chat_sessions(query, user)
            if method == "GET" and path == "/chat/messages":
                return self._chat_messages(query, user)

            # 推荐记录
            if method == "GET" and path == "/recommend/page":
                return self._recommend_page(query)

            # 营销文案与合规
            if method == "POST" and path == "/copy/generate":
                return self._copy_generate(body, user)
            if method == "GET" and path == "/copy/page":
                return self._copy_page(query)

            # 用户与角色
            if method == "GET" and path == "/system/user/list":
                if user.get("roleKey") != "admin":
                    return self._fail(403, "需要管理员权限")
                return self._ok([
                    {k: u[k] for k in ("id", "username", "password", "salt", "nickname",
                                       "roleId", "status", "roleKey", "roleName")}
                    for u in USERS
                ])
            if method == "GET" and path == "/system/role/list":
                return self._ok(ROLES)

            return self._fail(404, "接口不存在: %s %s" % (method, path))
        except ValueError as e:
            return self._fail(400, str(e))
        except Exception as e:  # pragma: no cover - 防御
            return self._fail(500, "服务内部错误: %s: %s" % (type(e).__name__, e))

    @staticmethod
    def _match(pattern: str, path: str):
        return re.match(pattern, path)

    # ---- 认证 ----

    def _login(self, body: dict) -> None:
        username = str(body.get("username") or "").strip()
        raw = str(body.get("password") or "")
        if not username or not raw:
            return self._fail(400, "账号和密码不能为空")
        user = next((u for u in USERS if u["username"] == username), None)
        if user is None:
            return self._fail(400, "账号不存在")
        if user.get("status") != 1:
            return self._fail(400, "账号已被停用，请联系管理员")
        if md5(user["salt"] + raw) != user["password"]:
            return self._fail(400, "密码错误")

        token = uuid.uuid4().hex
        info = {"id": user["id"], "username": user["username"], "nickname": user["nickname"],
                "roleKey": user["roleKey"], "roleName": user["roleName"]}
        with LOCK:
            TOKENS[token] = info
        return self._ok({"token": token, "user": info}, message="登录成功")

    def _logout(self) -> None:
        auth = self.headers.get("Authorization")
        token = auth[7:].strip() if auth and auth.startswith("Bearer ") else self.headers.get("token")
        if token:
            with LOCK:
                TOKENS.pop(token.strip(), None)
        return self._ok(None, message="已注销")

    # ---- 数据看板 ----

    def _dashboard_stats(self) -> None:
        today = today_prefix()
        with LOCK:
            today_chat = sum(1 for m in MESSAGES
                             if m["role"] == "user" and str(m["createTime"]).startswith(today))
            today_rec = sum(1 for r in RECOMMENDS if str(r["createTime"]).startswith(today))
            customer_count = len(CUSTOMERS)
            session_count = len(SESSIONS)
            total_copy = len(COPIES)
            passed_copy = sum(1 for c in COPIES if c.get("compliant") == 1)
            intent_counts = {}
            for m in MESSAGES:
                if m["role"] == "assistant" and m.get("intent"):
                    key = (m["intent"], m.get("intentZh") or "")
                    intent_counts[key] = intent_counts.get(key, 0) + 1
        distribution = [
            {"intent": k[0], "intent_zh": k[1], "cnt": v}
            for k, v in sorted(intent_counts.items(), key=lambda kv: -kv[1])
        ]
        return self._ok({
            "todayChatCount": today_chat,
            "todayRecommendCount": today_rec,
            "customerCount": customer_count,
            "sessionCount": session_count,
            "compliance": {
                "total": total_copy,
                "passed": passed_copy,
                "passRate": 1.0 if total_copy == 0 else passed_copy / total_copy,
            },
            "intentDistribution": distribution,
            "agentAvailable": self.agent.health(),
        })

    # ---- 客户 ----

    def _customer_page(self, query: dict) -> None:
        name = str(query.get("name") or "").strip()
        phone = str(query.get("phone") or "").strip()
        occupation = str(query.get("occupation") or "").strip()
        page_num = self._int_param(query, "pageNum", 1, 1, 10 ** 9)
        page_size = self._int_param(query, "pageSize", 10, 1, 100)
        with LOCK:
            rows = [dict(c) for c in CUSTOMERS]
        if name:
            rows = [c for c in rows if name in (c.get("name") or "")]
        if phone:
            rows = [c for c in rows if phone in (c.get("phone") or "")]
        if occupation:
            rows = [c for c in rows if c.get("occupation") == occupation]
        total = len(rows)
        start = (page_num - 1) * page_size
        return self._ok({"total": total, "pageNum": page_num, "pageSize": page_size,
                         "list": rows[start:start + page_size]})

    def _customer_detail(self, cid: int) -> None:
        with LOCK:
            customer = next((dict(c) for c in CUSTOMERS if c["id"] == cid), None)
        return self._ok(customer)

    def _customer_create(self, body: dict, user: dict) -> None:
        if not str(body.get("name") or "").strip():
            return self._fail(400, "客户姓名不能为空")
        with LOCK:
            customer = {
                "id": next_id(CUSTOMERS),
                "name": str(body.get("name")).strip(),
                "gender": body.get("gender") or "男",
                "phone": body.get("phone") or "",
                "age": body.get("age"),
                "occupation": body.get("occupation") or "",
                "monthlyIncome": body.get("monthlyIncome"),
                "creditStatus": body.get("creditStatus") or "",
                "remark": body.get("remark") or "",
                "createBy": user["username"],
                "createTime": now_iso(),
                "updateTime": now_iso(),
            }
            CUSTOMERS.append(customer)
        return self._ok(customer, message="新增成功")

    def _customer_update(self, cid: int, body: dict) -> None:
        with LOCK:
            customer = next((c for c in CUSTOMERS if c["id"] == cid), None)
            if customer is None:
                return self._ok(0, message="更新成功")
            for field in ("name", "gender", "phone", "age", "occupation",
                          "monthlyIncome", "creditStatus", "remark"):
                if field in body and body[field] is not None:
                    customer[field] = body[field]
            customer["updateTime"] = now_iso()
        return self._ok(1, message="更新成功")

    def _customer_delete(self, cid: int) -> None:
        with LOCK:
            before = len(CUSTOMERS)
            CUSTOMERS[:] = [c for c in CUSTOMERS if c["id"] != cid]
        return self._ok(1 if len(CUSTOMERS) < before else 0, message="删除成功")

    # ---- 产品 ----

    def _product_create(self, body: dict, user: dict) -> None:
        if user.get("roleKey") != "admin":
            return self._fail(403, "需要管理员权限")
        code = str(body.get("productCode") or "").strip()
        if not code:
            return self._fail(400, "产品编码不能为空")
        if not str(body.get("name") or "").strip():
            return self._fail(400, "产品名称不能为空")
        with LOCK:
            if any(p["productCode"] == code for p in PRODUCTS):
                return self._fail(400, "产品编码已存在: " + code)
            product = {
                "id": next_id(PRODUCTS),
                "productCode": code,
                "name": str(body.get("name")).strip(),
                "category": body.get("category") or "消费贷",
                "minAmount": body.get("minAmount") or 0,
                "maxAmount": body.get("maxAmount") or 0,
                "minTermMonths": body.get("minTermMonths") or 1,
                "maxTermMonths": body.get("maxTermMonths") or 36,
                "annualRateMin": body.get("annualRateMin") or 0,
                "annualRateMax": body.get("annualRateMax") or 0,
                "approvalHours": body.get("approvalHours") or 24,
                "minAge": body.get("minAge") or 18,
                "maxAge": body.get("maxAge") or 65,
                "minMonthlyIncome": body.get("minMonthlyIncome") or 0,
                "minCreditScore": body.get("minCreditScore") or 0,
                "allowedPurposes": body.get("allowedPurposes") or "",
                "tags": body.get("tags") or "",
                "description": body.get("description") or "",
                "status": body.get("status", 1),
                "createTime": now_iso(),
                "updateTime": now_iso(),
            }
            PRODUCTS.append(product)
        return self._ok(product, message="新增成功")

    def _product_update(self, pid: int, body: dict, user: dict) -> None:
        if user.get("roleKey") != "admin":
            return self._fail(403, "需要管理员权限")
        with LOCK:
            product = next((p for p in PRODUCTS if p["id"] == pid), None)
            if product is None:
                return self._ok(0, message="更新成功")
            for field in ("name", "category", "minAmount", "maxAmount", "minTermMonths",
                          "maxTermMonths", "annualRateMin", "annualRateMax", "approvalHours",
                          "minAge", "maxAge", "minMonthlyIncome", "minCreditScore",
                          "allowedPurposes", "tags", "description", "status"):
                if field in body and body[field] is not None:
                    product[field] = body[field]
            product["updateTime"] = now_iso()
        return self._ok(1, message="更新成功")

    def _product_delete(self, pid: int, user: dict) -> None:
        if user.get("roleKey") != "admin":
            return self._fail(403, "需要管理员权限")
        with LOCK:
            before = len(PRODUCTS)
            PRODUCTS[:] = [p for p in PRODUCTS if p["id"] != pid]
        return self._ok(1 if len(PRODUCTS) < before else 0, message="删除成功")

    # ---- 智能对话 ----

    def _chat_send(self, body: dict, user: dict) -> None:
        message = str(body.get("message") or "").strip()
        if not message:
            return self._fail(400, "消息内容不能为空")
        customer_id = body.get("customerId")
        session_id = body.get("sessionId")

        # 1) 会话：无则新建（session_id 对前端暴露的是数据库主键，Agent 侧用 session_no）
        with LOCK:
            if session_id is None:
                session = {
                    "id": next_id(SESSIONS),
                    "sessionNo": "S" + uuid.uuid4().hex[:16],
                    "userId": user["id"],
                    "customerId": customer_id,
                    "title": (message[:20] + "…") if len(message) > 20 else message,
                    "createTime": now_iso(),
                    "updateTime": now_iso(),
                }
                SESSIONS.append(session)
            else:
                try:
                    sid = int(session_id)
                except (TypeError, ValueError):
                    return self._fail(400, "会话不存在或无权访问")
                session = next((s for s in SESSIONS if s["id"] == sid), None)
                if session is None or session["userId"] != user["id"]:
                    return self._fail(400, "会话不存在或无权访问")
                if customer_id is not None and session.get("customerId") is None:
                    session["customerId"] = customer_id

            # 2) 客户消息落库
            self._save_message(session["id"], "user", message, "", "")

        # 3) 调用 Python Agent（锁外执行；失败降级 available=false）
        agent_data = self.agent.chat(session["sessionNo"], "u" + str(user["id"]), message,
                                     context=body.get("context"))
        available = agent_data.get("available") is True
        reply = str(agent_data.get("reply") or "")
        intent = str(agent_data.get("intent") or "")
        intent_zh = str(agent_data.get("intent_zh") or "")
        recs = agent_data.get("recommendations")

        with LOCK:
            # 4) 助手消息落库（降级回复同样落库，保证会话完整）
            self._save_message(session["id"], "assistant", reply, intent, intent_zh)

            # 5) 推荐记录归档（含四维评分明细 JSON）
            if available and isinstance(recs, list) and recs:
                try:
                    top = recs[0].get("product", {})
                    RECOMMENDS.append({
                        "id": next_id(RECOMMENDS),
                        "sessionId": session["id"],
                        "customerId": session.get("customerId"),
                        "userId": user["id"],
                        "message": message,
                        "topProduct": str(top.get("name") or ""),
                        "resultJson": json.dumps(
                            {"slots": agent_data.get("slots"), "recommendations": recs},
                            ensure_ascii=False),
                        "createTime": now_iso(),
                    })
                except Exception as e:
                    print("[mock-backend] 推荐记录归档失败（不影响主流程）: %s" % e,
                          file=sys.stderr)

            # 6) 会话活跃时间
            session["updateTime"] = now_iso()

        return self._ok({
            "session_id": session["id"],
            "session_no": session["sessionNo"],
            "reply": reply,
            "intent": intent,
            "intent_zh": intent_zh,
            "recommendations": recs,
            "actions": agent_data.get("actions") or [],
            "compliance": agent_data.get("compliance"),
            "memory_used": agent_data.get("memory_used"),
            "agent_available": available,
        })

    def _save_message(self, session_id: int, role: str, content: str,
                      intent: str, intent_zh: str) -> None:
        MESSAGES.append({
            "id": next_id(MESSAGES),
            "sessionId": session_id,
            "role": role,
            "content": content,
            "intent": intent,
            "intentZh": intent_zh,
            "createTime": now_iso(),
        })

    def _session_view(self, s: dict) -> dict:
        customer = next((c for c in CUSTOMERS if c["id"] == s.get("customerId")), None)
        return {
            "id": s["id"], "sessionNo": s["sessionNo"], "userId": s["userId"],
            "customerId": s.get("customerId"), "title": s.get("title") or "",
            "createTime": s["createTime"], "updateTime": s["updateTime"],
            "customerName": customer["name"] if customer else None,
        }

    def _chat_sessions(self, query: dict, user: dict) -> None:
        limit = self._int_param(query, "limit", 50, 1, 100)
        with LOCK:
            rows = [self._session_view(s) for s in SESSIONS if s["userId"] == user["id"]]
        rows.sort(key=lambda s: str(s["updateTime"]), reverse=True)
        return self._ok(rows[:limit])

    def _chat_messages(self, query: dict, user: dict) -> None:
        try:
            sid = int(query.get("sessionId") or 0)
        except (TypeError, ValueError):
            sid = 0
        with LOCK:
            session = next((s for s in SESSIONS if s["id"] == sid), None)
            if session is None or session["userId"] != user["id"]:
                return self._fail(400, "会话不存在或无权访问")
            rows = [dict(m) for m in MESSAGES if m["sessionId"] == sid]
        rows.sort(key=lambda m: m["id"])
        return self._ok(rows)

    # ---- 推荐记录 ----

    def _recommend_page(self, query: dict) -> None:
        customer_id_raw = query.get("customerId")
        try:
            customer_id = int(customer_id_raw) if customer_id_raw not in (None, "", "null") else None
        except (TypeError, ValueError):
            customer_id = None
        page_num = self._int_param(query, "pageNum", 1, 1, 10 ** 9)
        page_size = self._int_param(query, "pageSize", 10, 1, 100)
        with LOCK:
            rows = [dict(r) for r in RECOMMENDS]
            customers = {c["id"]: c["name"] for c in CUSTOMERS}
            users = {u["id"]: u["username"] for u in USERS}
        if customer_id is not None:
            rows = [r for r in rows if r.get("customerId") == customer_id]
        for r in rows:
            r["customerName"] = customers.get(r.get("customerId"))
            r["username"] = users.get(r.get("userId"))
        rows.sort(key=lambda r: r["id"], reverse=True)
        total = len(rows)
        start = (page_num - 1) * page_size
        return self._ok({"total": total, "pageNum": page_num, "pageSize": page_size,
                         "list": rows[start:start + page_size]})

    # ---- 营销文案与合规 ----

    def _copy_generate(self, body: dict, user: dict) -> None:
        product_id = str(body.get("productId") or "").strip()
        if not product_id:
            return self._fail(400, "产品编码不能为空")
        channel = str(body.get("channel") or "").strip() or "朋友圈"

        data = self.agent.generate_copy("u" + str(user["id"]), product_id, channel)
        if data is None:
            return self._fail(400, "智能文案服务暂时不可用，请确认 Python Agent 已启动后重试")

        compliance = data.get("compliance") or {}
        compliant = compliance.get("compliant") is True

        # 命中规则汇总（正则 rule_name + 语义 exemplar，与 Java CopyServiceImpl 一致）
        hits = []
        for h in compliance.get("regex_hits") or []:
            if isinstance(h, dict) and h.get("rule_name"):
                hits.append(str(h["rule_name"]))
        semantic = compliance.get("semantic") or {}
        for h in semantic.get("hits") or []:
            if isinstance(h, dict) and h.get("exemplar"):
                hits.append("语义相似: " + str(h["exemplar"]))

        with LOCK:
            record = {
                "id": next_id(COPIES),
                "userId": user["id"],
                "customerId": body.get("customerId"),
                "productId": str(data.get("product_id") or product_id),
                "productName": str(data.get("product_name") or ""),
                "channel": channel,
                "template": str(data.get("template") or ""),
                "content": str(data.get("text") or ""),
                "compliant": 1 if compliant else 0,
                "hitRules": json.dumps(hits, ensure_ascii=False),
                "conclusion": ("双重风控（正则+语义）审核通过" if compliant
                               else "命中 %d 条违规规则，建议修改后重新生成" % len(hits)),
                "createTime": now_iso(),
            }
            COPIES.append(record)
            view = dict(record)
            view["username"] = user["username"]

        return self._ok({
            "record": view,
            "compliance": compliance,
            "template_blocked": data.get("template_blocked"),
        })

    def _copy_page(self, query: dict) -> None:
        only_violation = str(query.get("onlyViolation") or "false").lower() == "true"
        page_num = self._int_param(query, "pageNum", 1, 1, 10 ** 9)
        page_size = self._int_param(query, "pageSize", 10, 1, 100)
        with LOCK:
            rows = [dict(c) for c in COPIES]
            users = {u["id"]: u["username"] for u in USERS}
        if only_violation:
            rows = [c for c in rows if c.get("compliant") == 0]
        for c in rows:
            c["username"] = users.get(c.get("userId"))
        rows.sort(key=lambda c: c["id"], reverse=True)
        total = len(rows)
        start = (page_num - 1) * page_size
        return self._ok({"total": total, "pageNum": page_num, "pageSize": page_size,
                         "list": rows[start:start + page_size]})


# ------------------------------------------------------------------ 服务装配


def make_server(host: str, port: int, agent_base: str) -> ThreadingHTTPServer:
    """host 含冒号时按 IPv6 绑定（Windows 默认双栈，同时接受 IPv4 回环）。
    这一点很关键：vite 代理 target 写的是 localhost，Node 17+ 会优先把
    localhost 解析成 ::1，若只绑 0.0.0.0 会导致代理连接被拒绝。"""
    if ":" in host:
        class _V6Server(ThreadingHTTPServer):
            address_family = socket.AF_INET6
        server = _V6Server((host, port), MockHandler)
    else:
        server = ThreadingHTTPServer((host, port), MockHandler)
    server.agent_bridge = AgentBridge(agent_base)  # type: ignore[attr-defined]
    server.daemon_threads = True
    return server


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="credit-agent-web 演示模式 Mock 后端")
    parser.add_argument("--host", default="::",
                        help="监听地址（默认 :: 双栈；失败自动回退 0.0.0.0）")
    parser.add_argument("--port", type=int, default=8080, help="监听端口（默认 8080）")
    parser.add_argument("--agent", default="http://127.0.0.1:8000",
                        help="Python Agent 地址（默认 http://127.0.0.1:8000）")
    args = parser.parse_args(argv)

    seed()
    try:
        server = make_server(args.host, args.port, args.agent)
        bound = args.host
    except OSError as e:
        if ":" not in args.host:
            raise
        print("[mock-backend] 绑定 %s 失败（%s），回退 0.0.0.0" % (args.host, e),
              file=sys.stderr)
        server = make_server("0.0.0.0", args.port, args.agent)
        bound = "0.0.0.0"

    print("=" * 64)
    print("  credit-agent-web 演示模式 Mock 后端")
    print("  监听: http://%s:%d%s  （内存数据，重启即重置）" % (bound, args.port, CONTEXT_PREFIX))
    print("  Agent 桥接: %s （/chat/send、/copy/generate）" % args.agent)
    print("  演示账号: admin / 123456 · manager01 / 123456")
    print("=" * 64)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
