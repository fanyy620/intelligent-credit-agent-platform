"""api_server 端点实测：随机端口起真实 HTTP 服务，用 urllib 发请求验证。

运行：python -m pytest tests/test_api_server.py -q
"""
from __future__ import annotations

import json
import threading
import urllib.request
import urllib.error

import pytest

from src.api_server import make_server


@pytest.fixture(scope="module")
def server_url():
    """在随机端口启动真实服务，测试结束优雅关闭。"""
    server = make_server(host="127.0.0.1", port=0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=3)


def _get(url: str) -> tuple[int, dict, dict]:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8")), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8")), dict(e.headers)


def _post(url: str, body: dict) -> tuple[int, dict, dict]:
    req = urllib.request.Request(
        url, method="POST",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8")), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8")), dict(e.headers)


# ------------------------------------------------------------------ health / products

def test_health(server_url):
    status, body, headers = _get(server_url + "/health")
    assert status == 200
    assert body["code"] == 0
    data = body["data"]
    assert data["status"] == "up"
    assert data["products"] >= 8
    assert "Access-Control-Allow-Origin" in headers  # CORS 放开


def test_products(server_url):
    _, body, _ = _get(server_url + "/v1/products")
    assert body["code"] == 0
    products = body["data"]
    assert len(products) >= 8
    for p in products:
        for key in ("id", "name", "category", "max_amount",
                    "annual_rate_min", "approval_hours", "allowed_purposes"):
            assert key in p, f"产品字段缺失: {key}"
    names = {p["name"] for p in products}
    assert "信享贷" in names


# ------------------------------------------------------------------ chat

def test_chat_recommend(server_url):
    _, body, _ = _post(server_url + "/v1/chat", {
        "session_id": "api-test-s1",
        "user_id": "api-test-u1",
        "message": "我月收入1万5，想借20万装修房子，3年内还清，征信良好，帮我推荐一下",
    })
    assert body["code"] == 0
    data = body["data"]
    assert data["intent"] == "CREDIT_RECOMMEND"
    assert data["reply"].strip()
    recs = data["recommendations"]
    assert recs, "推荐结果不能为空"
    top = recs[0]
    assert top["product"]["name"] == "信享贷"
    scores = top["scores"]
    for key in ("amount_score", "rate_score", "term_score",
                "speed_score", "business_score", "final_score"):
        assert 0.0 <= scores[key] <= 1.0, f"{key} 越界"
    # 记忆生效：事实写入并在返回中体现
    assert data["memory_used"]["facts_written"].get("借款用途") == "装修"


def test_chat_multi_turn_memory(server_url):
    url = server_url + "/v1/chat"
    _post(url, {"session_id": "api-test-s2", "user_id": "api-test-u2",
                "message": "我想借20万装修，帮我推荐一下"})
    _, body, _ = _post(url, {"session_id": "api-test-s2", "user_id": "api-test-u2",
                             "message": "针对这款产品写一段朋友圈文案"})
    data = body["data"]
    assert data["intent"] == "COPYWRITING"
    assert "信享贷" in data["reply"] or "{" not in data["reply"]
    # 第二轮应读到第一轮的历史
    assert data["memory_used"]["history_len"] >= 2


def test_chat_param_validation(server_url):
    _, body, _ = _post(server_url + "/v1/chat", {"session_id": "", "message": "你好"})
    assert body["code"] == 400


def test_chat_actions_with_context(server_url):
    """携带页面上下文：抽取网站动作（Copilot 模式，Mock 确定性规则）。"""
    _, body, _ = _post(server_url + "/v1/chat", {
        "session_id": "api-test-act1", "user_id": "api-test-u1",
        "message": "最近业务数据怎么样", "context": {"page": "/dashboard"},
    })
    assert body["code"] == 0
    assert body["data"]["actions"] == [{"type": "show_stats", "params": {}}]


def test_chat_actions_empty_without_context(server_url):
    """不带 context：actions 为空数组，对话管线零影响。"""
    _, body, _ = _post(server_url + "/v1/chat", {
        "session_id": "api-test-act2", "user_id": "api-test-u1",
        "message": "最近业务数据怎么样",
    })
    assert body["code"] == 0
    assert body["data"]["actions"] == []


# ------------------------------------------------------------------ copy / compliance

def test_copy_generate(server_url):
    _, body, _ = _post(server_url + "/v1/copy/generate", {
        "user_id": "api-test-u1", "product_id": "xinxiangdai", "channel": "朋友圈",
    })
    assert body["code"] == 0
    data = body["data"]
    assert data["product_name"] == "信享贷"
    # 数值必须来自结构化数据而非模型编造
    assert "30万" in data["text"]
    assert "4.8%" in data["text"]
    assert "{" not in data["text"]  # 无残留槽位
    assert "以银行最终审核为准" in data["text"]  # 强制免责声明
    assert data["compliance"]["compliant"] is True


def test_copy_generate_unknown_product(server_url):
    _, body, _ = _post(server_url + "/v1/copy/generate",
                       {"product_id": "no-such-product"})
    assert body["code"] == 400


def test_compliance_check_blocks_violations(server_url):
    _, body, _ = _post(server_url + "/v1/compliance/check",
                       {"text": "本产品保本保息，百分百下款，无视黑白户"})
    assert body["code"] == 0
    data = body["data"]
    assert data["compliant"] is False
    rule_names = {h["rule_name"] for h in data["regex_hits"]}
    assert "承诺保本保息" in rule_names
    assert "承诺百分百下款" in rule_names
    assert "无视征信" in rule_names


def test_compliance_check_passes_clean_text(server_url):
    _, body, _ = _post(server_url + "/v1/compliance/check",
                       {"text": "信享贷最高可借30万，年化利率低至4.8%起，以审批结果为准"})
    assert body["data"]["compliant"] is True


# ------------------------------------------------------------------ 路由

def test_unknown_route_404(server_url):
    status, body, _ = _get(server_url + "/v1/not-exist")
    assert status == 404
    assert body["code"] == 404
