"""真实 LLM 联调测试（默认跳过，LIVE=1 时运行）。

    LIVE=1 python -m pytest tests/test_live_llm.py -q

LIVE=1 时 conftest 不再强制 LLM_PROVIDER=mock，provider 探测链
按环境真实 key 接入（本机：KIMI_API_KEY → kimi-for-coding）。
这些用例断言真实模型的关键行为，而非 mock 的确定性结果。
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("LIVE") != "1",
    reason="真实 LLM 联调：需 LIVE=1 且环境配置 KIMI_API_KEY/DEEPSEEK_API_KEY",
)

NCB_SENTENCE = "我们是制造业企业，需要200万流动资金贷款，期限12个月，请帮我推荐合适的信贷产品"


@pytest.fixture(scope="module")
def llm():
    from src.llm.client import get_llm

    client = get_llm()
    if getattr(client, "is_mock", False):
        pytest.skip("当前环境无真实 LLM Key（探测链落到 MockLLM）")
    return client


def test_live_backend_identity(llm):
    assert llm.backend_name in ("kimi", "deepseek")
    assert llm.model_name  # /health 依赖该字段暴露模型名


def test_live_intent_classification(llm):
    code, detail = llm.classify_intent(NCB_SENTENCE)
    assert code == "CREDIT_RECOMMEND"
    assert "失败降级" not in detail  # 必须是真实模型直出，而非降级结果


def test_live_slot_extraction(llm):
    slots = llm.extract_slots(NCB_SENTENCE, schema=[
        "amount", "term_months", "purpose", "occupation",
        "monthly_income", "age", "credit_status", "credit_score",
    ])
    assert slots.get("amount") == 2000000
    assert slots.get("term_months") == 12
    assert slots.get("purpose") in ("经营", "周转")


def test_live_copy_template_no_numbers(llm):
    from src.compliance import template_fill

    template = llm.gen_copy_template("税易贷")
    assert "{" in template  # 含槽位
    assert template_fill.find_free_numbers(template) == []  # 无越权数字


ADVISORY_REPLY = (
    "根据您的情况，为您推荐以下产品（按综合评分排序）：\n"
    "  Top1 税易贷（经营贷）综合分 0.614\n"
    "      额度10-300万，年化3.85%-6.5%，6-36个月，最快48小时审批\n"
    "      推荐理由：您为企业主且用于经营，税易贷基于纳税记录提供融资支持。\n"
    "以上额度和利率均以最终审批为准。"
)


def test_live_review_passes_advisory_reply(llm):
    """顾问式推荐回复（含 Top1 中性排序标签）不得被判违规——回归“首选事件”。"""
    assert llm.review_compliance(ADVISORY_REPLY) is True


def test_live_full_turn_pipeline(llm):
    """端到端：真实意图 + 真实槽位进入推荐流水线，产出非罐头回复。"""
    from src.agent.graph import build_context, run_turn

    ctx = build_context()
    state = run_turn(NCB_SENTENCE, user_id="live-u1", session_id="live-s1", ctx=ctx)
    assert state["intent"] == "CREDIT_RECOMMEND"
    assert state.get("recommendation"), "应产生推荐结果"
    top1 = state["recommendation"][0]
    assert top1.llm_reason, "推荐理由应来自真实 LLM"
    assert state["answer"].strip()
    # 对话回复必须是顾问式自然语言，不得被误拦、不得换成营销模板
    assert not state.get("blocked", False), "顾问回复不应被合规拦截"
    assert "好帮手" not in state["answer"]
    assert "合规拦截" not in state["answer"]
