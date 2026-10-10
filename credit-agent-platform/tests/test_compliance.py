"""双重风控单测：正则拦截 / 语义审核 / 模板填充（零外部依赖）。"""
from __future__ import annotations

import pytest

from src.compliance import regex_guard, semantic_guard, template_fill
from src.recommend.catalog import get_catalog


@pytest.fixture(scope="module")
def product():
    return next(p for p in get_catalog() if p.name == "信享贷")


# ------------------------------------------------------------------ 正则

@pytest.mark.parametrize("bad_text,rule_name", [
    ("这款产品保本保息，放心买", "承诺保本保息"),
    ("百分百下款，不批不要钱", "承诺百分百下款"),
    ("无视黑白户都能办理", "无视征信"),
    ("黑户可做，不看征信", "无视征信"),
    ("稳赚不赔的好机会", "承诺收益"),
    ("我们有银行内部渠道", "内部渠道包装"),
    ("零利息贷款，快来", "隐瞒费用/零费用噱头"),
])
def test_regex_guard_blocks_violations(bad_text, rule_name):
    hits = regex_guard.check(bad_text)
    assert hits, f"应拦截: {bad_text}"
    assert any(h.rule_name == rule_name for h in hits)


def test_regex_guard_passes_compliant_text():
    ok_text = ("信享贷最高可借30万，年化利率低至4.8%起，"
               "具体额度和利率以审批结果为准，请理性借贷。")
    assert regex_guard.is_compliant(ok_text)


def test_regex_redact_marks_violations():
    out = regex_guard.redact("保本保息，百分百下款")
    assert "违规话术已拦截" in out
    # 占位符不泄露违规词本身
    assert "保本" not in out
    assert "百分百" not in out


# ------------------------------------------------------------------ 语义审核

def test_semantic_guard_flags_paraphrase():
    # 换皮表达：不含任何正则关键词，但与违规样本语义相近
    text = "不管你征信情况怎么样，我们都可以给你放款"
    verdict = semantic_guard.check_semantic(text)
    assert verdict.method == "hash-embedding"
    # 该句与“不管你征信多差都可以放款”高度相似，应命中
    assert not verdict.passed or verdict.hits == []  # 伪embedding下宽松断言
    assert verdict.hits, "语义审核应命中相似违规样本"


def test_semantic_guard_passes_clean_text():
    verdict = semantic_guard.check_semantic("请问信享贷的还款方式有哪些")
    assert verdict.passed


# ------------------------------------------------------------------ 模板填充

def test_render_copy_fills_slots(product):
    data = template_fill.product_slot_data(product)
    result = template_fill.render_copy(template_fill.GOOD_LLM_TEMPLATE, data)
    assert result.ok
    # 数值来自结构化数据，而不是模型编造
    assert "30万" in result.text      # max_amount = 300000
    assert "4.8%" in result.text      # annual_rate_min = 0.048
    assert "{" not in result.text     # 无残留槽位
    assert template_fill.DISCLAIMER in result.text  # 强制免责声明


def test_render_copy_rejects_free_numbers(product):
    # 模型越权在模板里写了数字 → 整篇拒绝
    bad_template = "最高可借50万，年化{rate_min}起，快来申请"
    data = template_fill.product_slot_data(product)
    result = template_fill.render_copy(bad_template, data)
    assert not result.ok
    assert "50万" in result.free_numbers


def test_find_free_numbers_ignores_slots():
    template = "额度{max_amount}，利率{rate_min}起，最快{approval_hours}小时"
    assert template_fill.find_free_numbers(template) == ["小时"] or \
        template_fill.find_free_numbers(template) == []
    # 槽位内的数字不算游离；注意 {approval_hours}小时 中的“小时”是单位词，
    # 不含数字，故不应命中 FREE_NUMBER_PATTERN
    assert template_fill.find_free_numbers(template) == []


def test_render_copy_missing_slot_data(product):
    result = template_fill.render_copy("额度{max_amount}，{unknown_slot}", {"max_amount": "30万"})
    assert not result.ok
    assert "unknown_slot" in result.missing_slots


def test_bad_demo_copy_is_actually_blocked():
    # 对照实验中的“错误姿势”文案必须被风控命中（防止示例本身失真）
    hits = regex_guard.check(template_fill.BAD_LLM_RAW_COPY)
    rule_names = {h.rule_name for h in hits}
    assert {"承诺保本保息", "承诺百分百下款", "无视征信"} & rule_names
