# -*- coding: utf-8 -*-
"""中金方法论优化层测试：双视角辩论 / PIT 条款 / 经验库。

运行：python -m pytest tests/test_debate.py -q
全部离线（MockLLM），不触网。
"""
from __future__ import annotations

import json

import pytest

from src.agent.graph import build_context
from src.agent.nodes import RuntimeContext
from src.api_server import handle_chat
from src.debate import detect_hard_issues, run_debate
from src.llm import prompts
from src.llm.client import MockLLM, _sanitize_debate
from src.memory.experience import Experience, ExperienceStore, similarity
from src.recommend.catalog import Product
from src.recommend.recall import Candidate
from src.recommend.rerank import RankedItem


# ------------------------------------------------------------------ 工具

def _product(name="税易贷", max_amount=3000000, category="经营贷") -> Product:
    return Product(id=name, name=name, category=category,
                   min_amount=100000, max_amount=max_amount,
                   min_term_months=6, max_term_months=36,
                   annual_rate_min=0.0385, annual_rate_max=0.065,
                   approval_hours=48, min_age=22, max_age=60,
                   min_monthly_income=0, min_credit_score=550,
                   allowed_purposes=["经营", "周转"])


def _ranked(product: Product, score: float) -> RankedItem:
    return RankedItem(candidate=Candidate(product=product, rule_passed=True),
                      final_score=score)


def _ctx() -> RuntimeContext:
    return build_context()  # conftest 已强制 LLM_PROVIDER=mock


# ------------------------------------------------------------------ PIT 条款存在性

def test_pit_clause_in_slot_reply_debate_prompts():
    for builder, args in (
        (prompts.slot_messages, ("借20万装修", ["amount"])),
        (prompts.reply_messages, ("税易贷", {"amount": 2000000})),
        (prompts.debate_messages, ("risk", "税易贷", {"amount": 2000000})),
    ):
        system = builder(*args)[0]["content"]
        assert "PIT 时点约束" in system
        assert "不得假设或推断用户未提供的财务数据" in system


def test_debate_prompt_unknown_perspective_raises():
    with pytest.raises(ValueError):
        prompts.debate_messages("unknown", "税易贷", {})


# ------------------------------------------------------------------ 辩论意见解析（第二道闸）

def test_sanitize_debate_valid_passthrough():
    raw = {"stance": "反对", "points": ["偿付压力大"], "suggested_caveats": ["补流水"],
           "score_adjust": -0.1}
    out = _sanitize_debate(raw)
    assert out["stance"] == "反对" and out["points"] == ["偿付压力大"]
    assert out["score_adjust"] == -0.1


def test_sanitize_debate_normalizes():
    out = _sanitize_debate({"stance": "强烈推荐", "points": "不是数组",
                            "suggested_caveats": [123, ""], "score_adjust": 9.9})
    assert out["stance"] == "谨慎支持"      # 越枚举归一中间态
    assert out["points"] == []               # 非数组丢弃
    assert out["suggested_caveats"] == ["123"]
    assert out["score_adjust"] == 0.2        # 钳制上限
    with pytest.raises(ValueError):
        _sanitize_debate(["不是dict"])


# ------------------------------------------------------------------ Mock 视角意见（离线降级）

def test_mock_debate_structure_and_growth():
    mock = MockLLM()
    growth = mock.debate_perspective("growth", "税易贷",
                                     {"purpose": "周转", "occupation": "企业主", "amount": 2000000})
    assert growth["stance"] == "支持"
    assert any("周转" in p for p in growth["points"])
    risk = mock.debate_perspective("risk", "税易贷", {"amount": 2000000})
    assert set(risk) == {"stance", "points", "suggested_caveats", "score_adjust"}
    assert risk["suggested_caveats"]  # 无收入/征信信息必有提示


def test_mock_risk_opposes_high_leverage():
    risk = MockLLM().debate_perspective(
        "risk", "税易贷", {"monthly_income": 10000, "amount": 2000000})
    assert risk["stance"] == "反对"


# ------------------------------------------------------------------ 硬伤检测与裁决

def test_detect_hard_issues():
    p = _product()
    assert detect_hard_issues(p, {"monthly_income": 10000, "amount": 2000000})
    assert detect_hard_issues(p, {"monthly_income": 100000, "amount": 2000000}) == []
    assert detect_hard_issues(p, {"amount": 2000000}) == []  # 无收入信息不构成硬伤


def test_run_debate_hard_issue_triggers_top2_reeval():
    ranked = [_ranked(_product("税易贷"), 0.59), _ranked(_product("兴业经营贷", 1000000), 0.55)]
    slots = {"monthly_income": 10000, "amount": 2000000, "purpose": "周转"}
    result = run_debate(ranked, slots, llm=MockLLM())
    assert result is not None
    assert result.hard_issues                       # 规则硬伤
    assert result.reevaluated_top2 is True
    assert "兴业经营贷" in result.top2_note
    assert result.risk_notice                       # 风险提示分区非空
    d = result.to_dict()
    assert d["risk_view"]["role"] == "risk" and d["growth_view"]["role"] == "growth"


def test_run_debate_normal_case_no_reeval():
    ranked = [_ranked(_product("税易贷"), 0.59), _ranked(_product("兴业经营贷", 1000000), 0.55)]
    slots = {"monthly_income": 100000, "amount": 2000000, "purpose": "周转", "credit_status": "良好"}
    result = run_debate(ranked, slots, llm=MockLLM())
    assert result is not None
    assert result.hard_issues == []
    assert result.reevaluated_top2 is False
    assert result.top2_note == ""


class _BoomLLM(MockLLM):
    def debate_perspective(self, *a, **kw):
        raise RuntimeError("boom")


def test_run_debate_failure_degrades_to_none():
    ranked = [_ranked(_product("税易贷"), 0.59)]
    assert run_debate(ranked, {"amount": 2000000}, llm=_BoomLLM()) is None
    assert run_debate([], {"amount": 1}, llm=MockLLM()) is None  # 空推荐不辩论


# ------------------------------------------------------------------ 经验库

def test_experience_store_save_threshold_and_search():
    store = ExperienceStore()
    slots = {"purpose": "周转", "occupation": "企业主", "amount": 2000000, "term_months": 12}
    # 低于阈值不沉淀
    assert store.maybe_save([_ranked(_product(), 0.4)], slots, "s1") is None
    # 被拦截不沉淀
    assert store.maybe_save([_ranked(_product(), 0.6)], slots, "s1", blocked=True) is None
    # 高分沉淀
    exp = store.maybe_save([_ranked(_product(), 0.589)], slots, "s1")
    assert exp is not None and exp.product_name == "税易贷"

    hits = store.search_similar({"purpose": "周转", "occupation": "企业主", "amount": 1500000},
                                top_k=2, exclude_session="s2")
    assert hits and hits[0][0].product_name == "税易贷"
    assert hits[0][1] >= 0.7  # 用途+身份全中
    # 排除本会话
    assert store.search_similar(slots, exclude_session="s1") == []


def test_experience_similarity_monotonic():
    a = similarity({"purpose": "周转", "occupation": "企业主"},
                   {"purpose": "周转", "occupation": "企业主"})
    b = similarity({"purpose": "周转"},
                   {"purpose": "周转", "occupation": "企业主"})
    c = similarity({"purpose": "消费"},
                   {"purpose": "周转", "occupation": "企业主"})
    assert a == 0.7 and b == 0.4 and c == 0.0


# ------------------------------------------------------------------ 端到端（Mock，不触网）

def test_api_chat_recommend_has_debate_field():
    ctx = _ctx()
    res = handle_chat(ctx, {
        "session_id": "debate-t1", "user_id": "u1",
        "message": "我们是制造业企业，需要200万流动资金周转一年，请推荐合适产品",
    })
    assert res["intent"] == "CREDIT_RECOMMEND"
    debate = res["debate"]
    assert debate is not None
    assert debate["risk_view"]["role"] == "risk"
    assert debate["growth_view"]["role"] == "growth"
    assert debate["risk_notice"]            # 无收入/征信信息 → 必有风险提示
    assert "风险提示：" in res["reply"]      # 回复中可见辩论结果分区


def test_api_chat_chitchat_debate_none():
    res = handle_chat(_ctx(), {"session_id": "debate-t2", "user_id": "u1", "message": "你好"})
    assert res["debate"] is None


def test_api_debate_disabled_by_env(monkeypatch):
    monkeypatch.setenv("DEBATE_ENABLED", "0")
    ctx = build_context()
    assert ctx.debate_enabled is False
    res = handle_chat(ctx, {
        "session_id": "debate-t3", "user_id": "u1",
        "message": "我们是制造业企业，需要200万流动资金周转一年，请推荐合适产品",
    })
    assert res["debate"] is None
    assert "风险提示：" not in res["reply"]


def test_experience_flows_across_turns():
    """第一轮高分推荐沉淀经验 → 第二轮（新会话）检索命中并注入辩论上下文。"""
    ctx = _ctx()
    msg = "我们是制造业企业，需要200万流动资金周转一年，请推荐合适产品"
    res1 = handle_chat(ctx, {"session_id": "exp-s1", "user_id": "u-exp", "message": msg})
    assert res1["debate"] is not None
    assert len(ctx.experience_store) == 1  # 0.589 > 0.5 阈值，已沉淀

    res2 = handle_chat(ctx, {"session_id": "exp-s2", "user_id": "u-exp2", "message": msg})
    assert res2["debate"]["experiences_hint"]  # 第二轮命中经验库
    assert "税易贷" in res2["debate"]["experiences_hint"]
