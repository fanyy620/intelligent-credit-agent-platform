"""三层推荐架构单测（全程 mock，零外部依赖）。"""
from __future__ import annotations

import pytest

from src.recommend.catalog import get_catalog
from src.recommend.recall import rule_filter, rag_recall, recall_two_stage
from src.recommend.rerank import CatalogStats, RankWeights, rerank
from src.recommend.slots import SlotSet, extract_slots_rules


@pytest.fixture(scope="module")
def catalog():
    products = get_catalog()
    assert len(products) >= 8, "产品库至少需要 8 个产品"
    return products


@pytest.fixture(scope="module")
def stats(catalog):
    return CatalogStats.from_catalog(catalog)


# ------------------------------------------------------------------ 槽位抽取

def test_slot_extract_amount_term_purpose():
    slots = extract_slots_rules("我月收入1万5，想借20万装修房子，3年内还清，征信良好")
    assert slots.amount == 200000
    assert slots.term_months == 36
    assert slots.purpose == "装修"
    assert slots.monthly_income == 15000
    assert slots.credit_status == "良好"
    assert slots.credit_score == 650


def test_slot_extract_no_amount_when_only_income():
    # “月收入1万5”不能被误识别为借款金额
    slots = extract_slots_rules("我月收入1万5，想了解一下贷款")
    assert slots.monthly_income == 15000
    assert slots.amount is None


def test_slot_merge_override():
    base = SlotSet(amount=100000, purpose="经营")
    new = SlotSet(purpose="装修")
    merged = base.merge(new)
    assert merged.amount == 100000   # 未提供则继承
    assert merged.purpose == "装修"  # 提供则覆盖


# ------------------------------------------------------------------ 第一层：规则

def test_rule_filter_hard_constraints(catalog):
    slots = SlotSet(amount=200000, term_months=36, purpose="装修",
                    monthly_income=15000, credit_score=650)
    candidates = rule_filter(catalog, slots)
    passed = {c.product.name for c in candidates if c.rule_passed}
    rejected = {c.product.name: c.rule_reasons for c in candidates if not c.rule_passed}
    # 信享贷（30万/36月/装修）与安居房抵贷（20万起/120月/装修）应通过
    assert "信享贷" in passed
    assert "安居房抵贷" in passed
    # 极速信用贷最高 5 万，必须被拒且给出原因
    assert "极速信用贷" in rejected
    assert any("超出最高额度" in r for r in rejected["极速信用贷"])
    # 经营贷用途不匹配必须被拒
    assert "兴业经营贷" in rejected


def test_rule_filter_passes_when_slot_missing(catalog):
    # 未提供金额时不应误杀任何产品（金额维度）
    candidates = rule_filter(catalog, SlotSet(purpose="消费"))
    assert all(c.rule_passed for c in candidates if c.product.allowed_purposes and "消费" in c.product.allowed_purposes)


# ------------------------------------------------------------------ 第二层：语义

def test_rag_recall_scores_bounded_and_ranked(catalog):
    slots = SlotSet(amount=200000, purpose="装修")
    candidates = [c for c in rule_filter(catalog, slots) if c.rule_passed]
    ranked = rag_recall(candidates, "装修借20万 消费", top_k=None)
    assert all(0.0 <= c.semantic_score <= 1.0 for c in ranked)
    scores = [c.semantic_score for c in ranked]
    assert scores == sorted(scores, reverse=True), "应按语义分降序"
    # 与“装修消费”最相关的不应是经营贷
    assert ranked[0].product.category != "经营贷"


# ------------------------------------------------------------------ 第三层：重排

def test_rerank_score_formula(catalog, stats):
    slots = SlotSet(amount=200000, term_months=36, purpose="装修",
                    monthly_income=15000, credit_score=650)
    candidates = recall_two_stage(catalog, slots, raw_text="想借20万装修房子")
    weights = RankWeights()  # 默认 0.3/0.2/0.3/0.2，语义 0.25
    ranked = rerank(candidates, slots, stats, weights)

    assert ranked, "至少应有一个候选"
    finals = [it.final_score for it in ranked]
    assert finals == sorted(finals, reverse=True), "应按综合分降序"
    for it in ranked:
        assert 0.0 <= it.final_score <= 1.0
        # 公式自洽：final = (1-w)*business + w*semantic
        expect = (1 - weights.semantic) * it.business_score \
            + weights.semantic * it.candidate.semantic_score
        assert it.final_score == pytest.approx(expect, abs=1e-3)

    top1 = ranked[0].candidate.product
    assert top1.name == "信享贷", f"装修20万场景 Top1 应为信享贷，实际 {top1.name}"


def test_rerank_weights_must_sum_to_one(catalog, stats):
    bad = RankWeights(amount=0.9, term=0.9, rate=0.9, speed=0.9)
    with pytest.raises(ValueError):
        rerank([], SlotSet(), stats, bad)


def test_rerank_excludes_rule_rejected(catalog, stats):
    slots = SlotSet(amount=200000, purpose="经营")  # 消费贷全部用途不匹配
    candidates = recall_two_stage(catalog, slots, raw_text="经营周转")
    ranked = rerank(candidates, slots, stats, RankWeights())
    assert all(it.candidate.rule_passed for it in ranked)
