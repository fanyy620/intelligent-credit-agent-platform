"""MCP stdio 服务：利率查询 / 产品检索工具（原生 JSON-RPC 实现，零第三方依赖）。

=====================================================================
 踩坑记录：stdout 被日志污染导致 JSON-RPC 协议崩溃（真实事故复盘）
=====================================================================
MCP stdio 传输约定：stdout 是【纯协议通道】，只允许出现 JSON-RPC 消息，
一行一个 JSON。项目早期在代码里随手 print() 调试信息、logging 默认
输出到 stdout，结果客户端（Claude Desktop / MCP SDK）把日志行当
JSON 解析，直接抛出 "Unexpected token" 并断开连接，表现为“工具时灵
时不灵”，排查半天才发现是日志污染。

修法（本文件严格执行的三条纪律）：
1. logging 全部重定向到 stderr —— 见下方 logging.basicConfig(stream=sys.stderr)；
2. 禁止一切到 stdout 的 print —— 唯一的 stdout 写点是 _send() 中的
   sys.stdout.write(json.dumps(...))；
3. 第三方库若往 stdout 写，需在启动时用 contextlib.redirect_stdout
   兜底重定向到 stderr（本服务无第三方依赖，故无需兜底）。

验证方式：python -m src.mcp_server.server --selftest
=====================================================================
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# ---- 纪律 1：日志只走 stderr。stdout 永远只写 JSON-RPC 消息。 ----
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] mcp-server: %(message)s",
)
log = logging.getLogger("credit-mcp")

# 保证以脚本方式运行时也能 import 项目模块
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "credit-agent-mcp", "version": "0.1.0"}


# ------------------------------------------------------------------ 工具实现

def _tool_get_interest_rate(product_name: str) -> dict:
    """按产品名查利率区间（数据来自结构化产品库，绝不现场编造）。"""
    from src.recommend.catalog import get_catalog

    for p in get_catalog():
        if product_name in p.name or p.name in product_name or product_name == p.id:
            return {
                "found": True,
                "product": p.name,
                "annual_rate_range": p.rate_range_pct,
                "term_months": [p.min_term_months, p.max_term_months],
                "max_amount_wan": p.max_amount / 10000,
                "note": "具体利率以审批结果为准",
            }
    return {"found": False, "product": product_name,
            "candidates": [p.name for p in get_catalog()]}


def _tool_search_products(query: str, top_k: int = 3) -> dict:
    """语义检索产品（伪 embedding 降级实现，接口与 PGVector 版一致）。"""
    from src.recommend.catalog import get_catalog
    from src.utils.embedding import hash_embed, cosine

    q = hash_embed(query)
    scored = sorted(
        ((cosine(q, hash_embed(p.to_doc())), p) for p in get_catalog()),
        key=lambda x: x[0], reverse=True,
    )[: max(1, top_k)]
    return {
        "query": query,
        "results": [
            {"product": p.name, "category": p.category, "score": round(s, 4),
             "summary": p.summary()}
            for s, p in scored
        ],
    }


TOOLS = [
    {
        "name": "get_interest_rate",
        "description": "查询指定信贷产品的年化利率区间、期限与最高额度",
        "inputSchema": {
            "type": "object",
            "properties": {"product_name": {"type": "string", "description": "产品名，如 信享贷"}},
            "required": ["product_name"],
        },
    },
    {
        "name": "search_products",
        "description": "按自然语言描述语义检索信贷产品",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "需求描述，如 装修借20万"},
                "top_k": {"type": "integer", "default": 3},
            },
            "required": ["query"],
        },
    },
]


def _call_tool(name: str, arguments: dict) -> dict:
    if name == "get_interest_rate":
        return _tool_get_interest_rate(arguments.get("product_name", ""))
    if name == "search_products":
        return _tool_search_products(arguments.get("query", ""), int(arguments.get("top_k", 3)))
    raise ValueError(f"未知工具: {name}")


# ------------------------------------------------------------------ JSON-RPC

def _send(payload: dict) -> None:
    """纪律 2：这是全文件【唯一】的 stdout 写点，只写 JSON-RPC。"""
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _result(req_id, result: dict) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "result": result})


def _error(req_id, code: int, message: str) -> None:
    _send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def handle_message(msg: dict) -> None:
    method = msg.get("method", "")
    req_id = msg.get("id")
    log.info("收到请求 method=%s id=%s", method, req_id)  # → stderr

    if method == "initialize":
        _result(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })
    elif method == "ping":
        _result(req_id, {})
    elif method == "notifications/initialized":
        pass  # 通知无响应
    elif method == "tools/list":
        _result(req_id, {"tools": TOOLS})
    elif method == "tools/call":
        params = msg.get("params", {})
        try:
            output = _call_tool(params.get("name", ""), params.get("arguments", {}) or {})
            _result(req_id, {
                "content": [{"type": "text",
                             "text": json.dumps(output, ensure_ascii=False, indent=2)}],
                "isError": False,
            })
        except ValueError as e:
            _error(req_id, -32602, str(e))
        except Exception as e:  # 工具内部异常不能污染协议通道
            log.exception("工具执行异常")
            _error(req_id, -32603, f"工具执行异常: {e}")
    elif req_id is not None:
        _error(req_id, -32601, f"Method not found: {method}")


def serve() -> None:
    """stdio 主循环：逐行读取 JSON-RPC，EOF 退出。"""
    log.info("MCP stdio 服务已启动，等待客户端连接…")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            log.warning("忽略无法解析的输入行（前 60 字符）: %s", line[:60])
            continue
        handle_message(msg)
    log.info("stdin 关闭，服务退出")


def selftest() -> int:
    """自检：在进程内跑 initialize → tools/list → tools/call，
    验证协议闭环且 stdout 无日志污染。输出走 stderr。"""
    cases = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
         "params": {"name": "get_interest_rate", "arguments": {"product_name": "信享贷"}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call",
         "params": {"name": "search_products", "arguments": {"query": "装修借20万", "top_k": 2}}},
    ]
    ok = True
    for case in cases:
        import io

        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf  # 拦截协议输出做断言
        try:
            handle_message(case)
        finally:
            sys.stdout = old
        out = buf.getvalue().strip()
        try:
            parsed = json.loads(out)
            assert parsed.get("id") == case["id"], "响应 id 不匹配"
            assert "result" in parsed or "error" in parsed
            log.info("selftest method=%-12s -> OK (%d 字节协议输出)",
                     case["method"], len(out))
        except Exception as e:
            ok = False
            log.error("selftest method=%s -> FAIL: %s; 原始输出=%r",
                      case["method"], e, out[:120])
    log.info("selftest %s", "通过" if ok else "失败")
    return 0 if ok else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    serve()
