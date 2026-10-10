"""模板 + 数据后填充：从机制上杜绝“数值幻觉”。

问题：让 LLM 直接生成营销文案，它可能把“最高30万”写成“最高50万”，
把“年化4.8%起”写成“年化3.6%起”——数字张口就来，构成误导宣传。

方案：LLM 只产出【不含任何数字】的模板，数值一律来自结构化数据渲染：

    LLM 输出:  "【{product_name}】最高可借{max_amount}，年化利率低至{rate_min}起……"
    代码渲染:  max_amount ← product.max_amount / 10000  （唯一事实来源）

安全网：find_free_numbers() 会扫描模板，凡是不在 {} 槽位里的数字都视为
模型越权生成，整篇拒绝并要求重生成 —— 双重保障。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.recommend.catalog import Product

SLOT_PATTERN = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")
# 数字+金融单位的组合（模板中不允许游离存在）
FREE_NUMBER_PATTERN = re.compile(r"\d+(?:\.\d+)?\s*(?:万|元|块|%|％|个月|年|小时|天|分钟|厘|折)")

# 合规免责声明：由代码强制追加，模型无权删改
DISCLAIMER = "*具体额度、利率及审批结果以银行最终审核为准，请理性借贷。"


@dataclass
class RenderResult:
    ok: bool
    text: str = ""
    free_numbers: list[str] = field(default_factory=list)  # 模板中的越权数字
    missing_slots: list[str] = field(default_factory=list)  # 数据缺失的槽位
    error: str = ""


def find_free_numbers(template: str) -> list[str]:
    """找出模板中【不在槽位内】的数值表述。"""
    stripped = SLOT_PATTERN.sub("", template)
    return FREE_NUMBER_PATTERN.findall(stripped)


def product_slot_data(product: Product) -> dict[str, str]:
    """产品 → 渲染数据（唯一事实来源，数值全部来自结构化字段）。"""
    return {
        "product_name": product.name,
        "category": product.category,
        "max_amount": f"{product.max_amount / 10000:g}万",
        "min_amount": f"{product.min_amount / 10000:g}万",
        "rate_min": f"{product.annual_rate_min * 100:g}%",
        "rate_max": f"{product.annual_rate_max * 100:g}%",
        "min_term": str(product.min_term_months),
        "max_term": str(product.max_term_months),
        "approval_hours": f"{product.approval_hours:g}",
    }


def render_copy(template: str, data: dict[str, str], append_disclaimer: bool = True) -> RenderResult:
    """渲染模板：先查越权数字，再填槽，最后强制附免责声明。"""
    free = find_free_numbers(template)
    if free:
        return RenderResult(ok=False, free_numbers=free,
                            error="模板包含游离数字（疑似模型幻觉），已拒绝渲染")

    missing: list[str] = []

    def _sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in data:
            missing.append(key)
            return m.group(0)
        return str(data[key])

    text = SLOT_PATTERN.sub(_sub, template)
    if missing:
        return RenderResult(ok=False, missing_slots=missing,
                            error=f"以下槽位缺少数据：{missing}")
    if append_disclaimer and DISCLAIMER not in text:
        text = text.rstrip() + "\n" + DISCLAIMER
    return RenderResult(ok=True, text=text)


# ------------------------------------------------------------------ 对比演示

BAD_LLM_RAW_COPY = (
    "【信享贷】重磅上线！最高可借50万，年化利率低至3.6%，秒批秒到账，"
    "无视黑白户都能办，百分百下款，错过再等一年！"
)

GOOD_LLM_TEMPLATE = (
    "【{product_name}】您的{category}好帮手：最高可借{max_amount}，"
    "年化利率低至{rate_min}起，期限{min_term}-{max_term}个月灵活可选，"
    "最快{approval_hours}小时完成审批。线上申请，流程透明。"
)


def hallucination_contrast_demo(product: Product) -> str:
    """生成“错误姿势 vs 正确姿势”的对照说明，供 demo 与文档引用。"""
    data = product_slot_data(product)
    good = render_copy(GOOD_LLM_TEMPLATE, data)
    lines = [
        "—— 数值幻觉对照实验 ——",
        "",
        "[错误姿势] 让 LLM 直接生成含数字的文案（模型编造了不存在的“50万/3.6%/秒批”）：",
        f"  {BAD_LLM_RAW_COPY}",
        f"  正则风控命中：{[v.rule_name for v in _bad_check()]}",
        "",
        "[正确姿势] LLM 只生成模板槽位，数值由代码从结构化数据填充：",
        f"  模板: {GOOD_LLM_TEMPLATE}",
        f"  数据: max_amount={data['max_amount']}, rate_min={data['rate_min']}, approval_hours={data['approval_hours']}小时",
        "  成稿:",
    ]
    lines += [f"    {ln}" for ln in good.text.splitlines()]
    return "\n".join(lines)


def _bad_check():
    from src.compliance.regex_guard import check

    return check(BAD_LLM_RAW_COPY)
