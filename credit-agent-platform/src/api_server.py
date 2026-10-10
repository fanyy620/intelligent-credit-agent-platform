"""Python Agent HTTP 服务（仅标准库实现，零第三方依赖）。

为 SSM 业务后端提供智能能力：对话流水线、营销文案生成、合规审核、产品库查询。
复用项目现有模块（agent/graph、recommend、compliance、memory、intent），
不重写任何业务逻辑 —— 本文件只做“HTTP 壳”。

运行：python src/api_server.py [--host 0.0.0.0] [--port 8000]

线程模型：ThreadingHTTPServer。降级后端（内存字典）本身非严格线程安全，
高并发下极端情况可能出现窗口裁剪竞态，教学/演示场景可接受；
生产环境请换 Redis/PG 后端（配置 .env 即可，代码不变）。
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from configs.settings import get_settings                 # noqa: E402
from src.agent.graph import build_context, run_turn       # noqa: E402
from src.agent.nodes import RuntimeContext                # noqa: E402
from src.compliance import regex_guard, semantic_guard, template_fill  # noqa: E402
from src.recommend.catalog import Product                 # noqa: E402

API_VERSION = "v1"


# ------------------------------------------------------------------ 序列化

def _product_dict(p: Product) -> dict:
    return {
        "id": p.id, "name": p.name, "category": p.category,
        "min_amount": p.min_amount, "max_amount": p.max_amount,
        "min_term_months": p.min_term_months, "max_term_months": p.max_term_months,
        "annual_rate_min": p.annual_rate_min, "annual_rate_max": p.annual_rate_max,
        "rate_range_pct": p.rate_range_pct,
        "approval_hours": p.approval_hours,
        "min_age": p.min_age, "max_age": p.max_age,
        "min_monthly_income": p.min_monthly_income,
        "min_credit_score": p.min_credit_score,
        "allowed_purposes": p.allowed_purposes, "tags": p.tags,
        "description": p.description, "summary": p.summary(),
    }


def _recommendation_dict(item) -> dict:
    return {
        "product": _product_dict(item.candidate.product),
        "scores": {
            "amount_score": item.amount_score,
            "rate_score": item.rate_score,
            "term_score": item.term_score,
            "speed_score": item.speed_score,
            "business_score": item.business_score,
            "semantic_score": round(item.candidate.semantic_score, 4),
            "final_score": item.final_score,
        },
        "reason": item.llm_reason,
    }


def _compliance_dict(text: str, llm=None) -> dict:
    violations = regex_guard.check(text)
    verdict = semantic_guard.check_semantic(text, llm=llm)
    return {
        "compliant": not violations and verdict.passed,
        "regex_hits": [v.__dict__ for v in violations],
        "semantic": {
            "passed": verdict.passed,
            "method": verdict.method,
            "hits": [h.__dict__ for h in verdict.hits],
        },
    }


# ------------------------------------------------------------------ 业务处理

def handle_chat(ctx: RuntimeContext, body: dict) -> dict:
    """走完整 Agent 流水线（意图路由→分支→合规→记忆），返回结构化结果。

    可选 context {page, locale}：前端悬浮窗携带当前页面上下文时，
    额外抽取“网站动作列表”（Copilot 模式）；不带 context 时 actions=[],
    对既有对话管线零影响。
    """
    session_id = str(body.get("session_id") or "").strip()
    user_id = str(body.get("user_id") or "anonymous").strip()
    message = str(body.get("message") or "").strip()
    context = body.get("context")
    if not session_id:
        raise ValueError("session_id 不能为空")
    if not message:
        raise ValueError("message 不能为空")

    state = run_turn(message, user_id=user_id, session_id=session_id, ctx=ctx)
    mem = state.get("memory_context")

    actions: list[dict] = []
    if isinstance(context, dict) and context.get("page"):
        try:
            actions = ctx.llm.extract_site_actions(
                message, page=str(context.get("page"))[:40]) or []
        except Exception:
            actions = []  # 动作抽取失败绝不影响对话主链路

    return {
        "session_id": session_id,
        "intent": state.get("intent", ""),
        "intent_zh": state.get("intent_zh", ""),
        "intent_backend": state.get("intent_backend", ""),
        "reply": state.get("answer", ""),
        "actions": actions,
        "slots": state.get("slots", {}),
        "recommendations": [_recommendation_dict(it)
                            for it in state.get("recommendation", [])[:3]],
        # 双视角辩论裁决（中金方法论层）；非推荐意图/辩论降级时为 None，向后兼容
        "debate": state.get("debate"),
        "memory_used": {
            "history_len": mem.history_len if mem else 0,
            "facts": {f.fact_key: f.fact_value for f in (mem.facts if mem else [])},
            "facts_written": state.get("memory_facts_written", {}),
        },
        "compliance": {
            "blocked": state.get("blocked", False),
            "regex_hits": state.get("compliance_regex", []),
            "semantic": state.get("compliance_semantic", {}),
        },
        "trace_id": state.get("trace_id", ""),
    }


def handle_copy_generate(ctx: RuntimeContext, body: dict) -> dict:
    """模板填充生成营销文案 + 合规审核（LLM 只产模板，数值由结构化数据渲染）。"""
    product_id = str(body.get("product_id") or "").strip()
    channel = str(body.get("channel") or "朋友圈").strip()
    if not product_id:
        raise ValueError("product_id 不能为空")
    product = next((p for p in ctx.catalog if p.id == product_id), None)
    if product is None:
        raise ValueError(f"产品不存在: {product_id}（可用 GET /v1/products 查询）")

    template = ctx.llm.gen_copy_template(product.name)
    free_numbers = template_fill.find_free_numbers(template)
    template_blocked = False
    if free_numbers:
        # 模型越权生成数字 → 拒绝渲染，换内置安全模板
        template_blocked = True
        template = template_fill.GOOD_LLM_TEMPLATE
    rendered = template_fill.render_copy(template, template_fill.product_slot_data(product))
    if not rendered.ok:
        rendered = template_fill.render_copy(
            template_fill.GOOD_LLM_TEMPLATE, template_fill.product_slot_data(product))

    compliance = _compliance_dict(rendered.text, llm=ctx.llm)
    return {
        "product_id": product.id,
        "product_name": product.name,
        "channel": channel,
        "template": template,
        "text": rendered.text,
        "template_blocked": template_blocked,
        "blocked_numbers": free_numbers,
        "compliance": compliance,
    }


# ------------------------------------------------------------------ HTTP 壳

class AgentHTTPRequestHandler(BaseHTTPRequestHandler):
    """统一 JSON 响应 {code, message, data}；code=0 成功。CORS 全放开。"""

    server_version = "CreditAgentHTTP/0.1"

    # 日志走 stderr（与 MCP 服务同纪律：绝不污染协议通道）
    def log_message(self, fmt, *args):  # noqa: A003
        sys.stderr.write("[api_server] %s - %s\n" % (self.address_string(), fmt % args))

    # ---- 基础设施 ----
    @property
    def ctx(self) -> RuntimeContext:
        return self.server.app_ctx  # type: ignore[attr-defined]

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, token")
        self.end_headers()
        self.wfile.write(body)

    def _ok(self, data, message: str = "ok") -> None:
        self._send_json({"code": 0, "message": message, "data": data})

    def _fail(self, code: int, message: str, status: int = 200) -> None:
        self._send_json({"code": code, "message": message, "data": None}, status=status)

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

    def do_OPTIONS(self):  # noqa: N802
        self._send_json({"code": 0, "message": "ok", "data": None})

    # ---- 路由 ----
    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path.rstrip("/")
        try:
            if path == "/health":
                self._ok({
                    "status": "up",
                    "service": "credit-agent",
                    "version": API_VERSION,
                    "llm_backend": getattr(self.ctx.llm, "backend_name",
                                           "mock" if getattr(self.ctx.llm, "is_mock", False) else "unknown"),
                    "llm_model": getattr(self.ctx.llm, "model_name", ""),
                    "memory_backend": f"{self.ctx.memory.short.backend_name}+{self.ctx.memory.long.backend_name}",
                    "products": len(self.ctx.catalog),
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                })
            elif path == f"/{API_VERSION}/products":
                self._ok([_product_dict(p) for p in self.ctx.catalog])
            else:
                self._fail(404, f"接口不存在: {path}", status=404)
        except Exception as e:  # pragma: no cover - 防御
            self._fail(500, f"服务内部错误: {type(e).__name__}: {e}", status=500)

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path.rstrip("/")
        try:
            body = self._read_body()
            if path == f"/{API_VERSION}/chat":
                self._ok(handle_chat(self.ctx, body))
            elif path == f"/{API_VERSION}/copy/generate":
                self._ok(handle_copy_generate(self.ctx, body))
            elif path == f"/{API_VERSION}/compliance/check":
                text = str(body.get("text") or "")
                if not text.strip():
                    raise ValueError("text 不能为空")
                self._ok(_compliance_dict(text, llm=self.ctx.llm))
            else:
                self._fail(404, f"接口不存在: {path}", status=404)
        except ValueError as e:
            self._fail(400, str(e), status=200)
        except Exception as e:  # pragma: no cover - 防御
            self._fail(500, f"服务内部错误: {type(e).__name__}: {e}", status=500)


def make_server(host: str = "0.0.0.0", port: int = 8000,
                ctx: RuntimeContext | None = None) -> ThreadingHTTPServer:
    """构建服务实例（port=0 时由系统分配随机端口，测试用）。"""
    if ctx is None:
        ctx = build_context(get_settings())
    server = ThreadingHTTPServer((host, port), AgentHTTPRequestHandler)
    server.app_ctx = ctx  # type: ignore[attr-defined]
    server.daemon_threads = True
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="信贷 Agent HTTP 服务（标准库实现）")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    server = make_server(args.host, args.port)
    actual = server.server_address
    print(f"[api_server] 信贷 Agent 服务已启动: http://{actual[0]}:{actual[1]}", file=sys.stderr)
    _llm = server.app_ctx.llm
    _llm_desc = (f"{getattr(_llm, 'backend_name', 'unknown')}"
                 f"({getattr(_llm, 'model_name', '') or 'deterministic'})")
    print(f"[api_server] LLM={_llm_desc}  "
          f"记忆={server.app_ctx.memory.short.backend_name}+{server.app_ctx.memory.long.backend_name}  "
          f"产品={len(server.app_ctx.catalog)}个", file=sys.stderr)
    print(f"[api_server] 端点: GET /health, GET /v1/products, "
          f"POST /v1/chat, POST /v1/copy/generate, POST /v1/compliance/check", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[api_server] 收到中断信号，正在退出…", file=sys.stderr)
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
