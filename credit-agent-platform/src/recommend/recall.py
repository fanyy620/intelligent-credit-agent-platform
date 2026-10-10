"""三层推荐架构之【前两层】：规则硬过滤 + RAG 语义召回。

第一层 rule_filter：基于产品 YAML 中的硬性准入字段（额度区间、期限区间、
用途白名单、收入门槛、年龄区间、征信分门槛）做确定性过滤，保证召回结果
100% 满足合规准入 —— 这是“宁可少推、不可错推”的业务底线。

第二层 rag_recall：把用户诉求与产品文档向量化，做语义相关性打分。
有 PGVector 时走数据库内向量检索；无 PGVector 时降级为纯 Python
哈希伪 embedding + 余弦相似度（接口不变、分数域不变）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.recommend.catalog import Product
from src.recommend.slots import SlotSet
from src.utils.embedding import hash_embed, cosine


@dataclass
class Candidate:
    """召回阶段的产品候选，携带两层的诊断信息供重排与展示。"""

    product: Product
    rule_passed: bool
    rule_reasons: list[str] = field(default_factory=list)   # 未通过原因
    semantic_score: float = 0.0                              # 第二层语义分 ∈ [-1, 1]
    embedding: list[float] | None = None


# ------------------------------------------------------------------ 第一层：规则

def _check(product: Product, slots: SlotSet) -> list[str]:
    """返回未通过的硬性规则原因列表；空列表 = 通过。未提供的槽位不做过滤。"""
    reasons: list[str] = []
    if slots.amount is not None:
        if slots.amount < product.min_amount:
            reasons.append(f"期望金额{slots.amount / 10000:g}万低于起借线{product.min_amount / 10000:g}万")
        if slots.amount > product.max_amount:
            reasons.append(f"期望金额{slots.amount / 10000:g}万超出最高额度{product.max_amount_wan}")
    if slots.term_months is not None:
        if not (product.min_term_months <= slots.term_months <= product.max_term_months):
            reasons.append(
                f"期限{slots.term_months}个月不在{product.min_term_months}-{product.max_term_months}个月区间内"
            )
    if slots.purpose is not None and product.allowed_purposes:
        if slots.purpose not in product.allowed_purposes:
            reasons.append(f"用途“{slots.purpose}”不在准入用途{product.allowed_purposes}内")
    if slots.monthly_income is not None:
        if slots.monthly_income < product.min_monthly_income:
            reasons.append(f"月收入{slots.monthly_income:g}低于准入线{product.min_monthly_income:g}")
    if slots.age is not None:
        if not (product.min_age <= slots.age <= product.max_age):
            reasons.append(f"年龄{slots.age}岁不在{product.min_age}-{product.max_age}岁区间内")
    if slots.credit_score is not None:
        if slots.credit_score < product.min_credit_score:
            reasons.append(f"估算征信分{slots.credit_score}低于准入线{product.min_credit_score}")
    return reasons


def rule_filter(products: list[Product], slots: SlotSet) -> list[Candidate]:
    """第一层：对每个产品打通过/拒绝标，全部返回（拒绝项保留原因便于解释）。"""
    out: list[Candidate] = []
    for p in products:
        reasons = _check(p, slots)
        out.append(Candidate(product=p, rule_passed=not reasons, rule_reasons=reasons))
    return out


# ------------------------------------------------------------------ 第二层：语义

def build_query_text(slots: SlotSet, raw_text: str = "") -> str:
    """把槽位拼成查询文本，增强伪 embedding 下的关键词重合度。"""
    parts = [raw_text]
    if slots.purpose:
        parts.append(slots.purpose)
    if slots.occupation:
        parts.append(slots.occupation)
    if slots.amount:
        parts.append(f"借款{slots.amount / 10000:g}万")
    if slots.term_months:
        parts.append(f"期限{slots.term_months}个月")
    return " ".join(p for p in parts if p)


def rag_recall(
    candidates: list[Candidate],
    query_text: str,
    dim: int = 256,
    top_k: int | None = None,
) -> list[Candidate]:
    """第二层：为候选打语义分（PGVector 的降级实现）。

    真实环境替换点：把 hash_embed 换为 bge/text2vec 向量，
    并把逐条 cosine 换成 PGVector 的 <=> 运算符 + ivfflat 索引。
    """
    q_vec = hash_embed(query_text, dim=dim)
    for c in candidates:
        if c.embedding is None:
            c.embedding = hash_embed(c.product.to_doc(), dim=dim)
        # 映射到 [0,1] 区间，方便与业务分加权融合
        c.semantic_score = max(0.0, cosine(q_vec, c.embedding))
    ranked = sorted(candidates, key=lambda c: c.semantic_score, reverse=True)
    if top_k is not None:
        return ranked[:top_k]
    return ranked


def recall_two_stage(
    products: list[Product],
    slots: SlotSet,
    raw_text: str = "",
    dim: int = 256,
) -> list[Candidate]:
    """前两层串联：规则过滤 → 仅对通过项打语义分，按语义分排序返回。"""
    candidates = rule_filter(products, slots)
    passed = [c for c in candidates if c.rule_passed]
    ranked = rag_recall(passed, build_query_text(slots, raw_text), dim=dim)
    # 拒绝项附在末尾，供 demo / 日志展示拒绝原因
    rejected = [c for c in candidates if not c.rule_passed]
    return ranked + rejected
