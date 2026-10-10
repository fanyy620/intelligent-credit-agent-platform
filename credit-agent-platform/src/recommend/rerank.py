"""三层推荐架构之【第三层】：多维业务评分 + 可选 LLM 重排。

业务评分公式（四个维度均为 0-1 分，权重可配置，默认和为 1）：

    business = w_amount * 额度匹配度
             + w_rate   * 利率优惠度
             + w_term   * 期限灵活度
             + w_speed  * 审批速度分

    final = (1 - semantic_weight) * business + semantic_weight * 语义分

调优要点见 docs/implementation-guide.md 第 3 节。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.recommend.catalog import Product
from src.recommend.recall import Candidate
from src.recommend.slots import SlotSet


@dataclass
class RankWeights:
    amount: float = 0.30
    term: float = 0.20
    rate: float = 0.30
    speed: float = 0.20
    semantic: float = 0.25  # 最终融合时的语义分权重

    def validate(self) -> None:
        s = self.amount + self.term + self.rate + self.speed
        if abs(s - 1.0) > 1e-6:
            raise ValueError(f"业务评分权重之和必须为 1.0，当前为 {s}")
        if not (0.0 <= self.semantic <= 1.0):
            raise ValueError("semantic 权重必须在 [0,1]")


@dataclass
class CatalogStats:
    """全量产品的归一化基准（在目录层面而非候选层面归一，保证分数可比）。"""

    min_rate: float
    max_rate: float
    min_hours: float
    max_hours: float

    @classmethod
    def from_catalog(cls, products: list[Product]) -> "CatalogStats":
        return cls(
            min_rate=min(p.annual_rate_min for p in products),
            max_rate=max(p.annual_rate_min for p in products),
            min_hours=min(p.approval_hours for p in products),
            max_hours=max(p.approval_hours for p in products),
        )


@dataclass
class RankedItem:
    candidate: Candidate
    amount_score: float = 0.0
    rate_score: float = 0.0
    term_score: float = 0.0
    speed_score: float = 0.0
    business_score: float = 0.0
    final_score: float = 0.0
    llm_reason: str = ""
    breakdown: dict = field(default_factory=dict)


def _norm(value: float, lo: float, hi: float, invert: bool = False) -> float:
    """min-max 归一化到 [0,1]；invert=True 时值越小分越高。"""
    if hi <= lo:
        return 1.0
    x = (value - lo) / (hi - lo)
    x = max(0.0, min(1.0, x))
    return 1.0 - x if invert else x


def business_score(
    product: Product,
    slots: SlotSet,
    stats: CatalogStats,
    weights: RankWeights,
) -> tuple[float, dict]:
    """计算单个产品的业务分与四维明细。"""
    # 额度匹配度：衡量“贴合度”而非“富余度”。规则层已保证 req <= max，
    # 但 max 远大于 req 的产品（如 500 万房抵贷服务 20 万装修）属于
    # “用大炮打蚊子”，真实业务不会推荐 —— 故 max/req ∈ [1,3] 为理想区间，
    # 超出 3 倍后线性衰减，最低 0.2。
    if slots.amount:
        ratio = product.max_amount / max(slots.amount, 1.0)
        if ratio <= 3.0:
            amount_score = 0.7 + 0.3 * (ratio - 1.0) / 2.0
        else:
            amount_score = max(0.2, 1.0 - 0.06 * (ratio - 3.0))
    else:
        amount_score = 0.8  # 未提供金额时给中性偏高分，不惩罚

    # 利率优惠度：以产品最低年化在全网产品区间中的位置打分，越低越高分
    rate_score = _norm(product.annual_rate_min, stats.min_rate, stats.max_rate, invert=True)

    # 期限灵活度：可贷最长期限相对用户诉求的覆盖能力
    if slots.term_months:
        term_score = min(1.0, product.max_term_months / (slots.term_months * 1.5))
    else:
        term_score = min(1.0, product.max_term_months / 60.0)

    # 审批速度：审批时效在全网产品区间中归一，越快越高分
    speed_score = _norm(product.approval_hours, stats.min_hours, stats.max_hours, invert=True)

    score = (
        weights.amount * amount_score
        + weights.rate * rate_score
        + weights.term * term_score
        + weights.speed * speed_score
    )
    breakdown = {
        "amount_score": round(amount_score, 4),
        "rate_score": round(rate_score, 4),
        "term_score": round(term_score, 4),
        "speed_score": round(speed_score, 4),
        "business_score": round(score, 4),
    }
    return score, breakdown


def rerank(
    candidates: list[Candidate],
    slots: SlotSet,
    stats: CatalogStats,
    weights: RankWeights | None = None,
    llm=None,
    use_llm: bool = False,
) -> list[RankedItem]:
    """第三层主入口：业务评分融合语义分排序；可选 LLM 对 Top3 复排。

    LLM 复排只做“解释与微调”：默认实现不改变顺序，仅生成推荐理由；
    真实环境下可让 LLM 基于用户画像在 Top3 内交换顺序，交换幅度被
    限制在 ±1 名，防止模型把硬性低分产品顶到首位（评分是底线）。
    """
    weights = weights or RankWeights()
    weights.validate()

    items: list[RankedItem] = []
    for c in candidates:
        if not c.rule_passed:
            continue
        biz, breakdown = business_score(c.product, slots, stats, weights)
        final = (1 - weights.semantic) * biz + weights.semantic * c.semantic_score
        items.append(
            RankedItem(
                candidate=c,
                amount_score=breakdown["amount_score"],
                rate_score=breakdown["rate_score"],
                term_score=breakdown["term_score"],
                speed_score=breakdown["speed_score"],
                business_score=breakdown["business_score"],
                final_score=round(final, 4),
                breakdown={**breakdown, "semantic_score": round(c.semantic_score, 4),
                           "final_score": round(final, 4)},
            )
        )
    items.sort(key=lambda x: x.final_score, reverse=True)

    if use_llm and llm is not None and items:
        for it in items[:3]:
            try:
                it.llm_reason = llm.explain_recommendation(
                    it.candidate.product.name, slots.filled()
                )
            except Exception:
                it.llm_reason = ""
    return items
