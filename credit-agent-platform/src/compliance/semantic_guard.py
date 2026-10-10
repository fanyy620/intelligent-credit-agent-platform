"""双重风控之【第二重】：语义审核。

正则只能拦截“写明的坏话术”，对换皮变体（如“保证都能批下来”）无能为力。
本模块用向量相似度把待审文本与违规话术样本库比对，命中近义表达即告警；
有 LLM 时可用 LLM 复核（可选增强），两者都不可用时自动降级为“仅正则”。

降级策略：
- 无 LLM（离线 demo）：hash 伪 embedding + 余弦相似度作为唯一语义层；
- 有 LLM：llm.review_compliance(text) 返回结构化结论，作为第二意见；
  营销文案场景两者叠加（宁严勿宽），对话回复场景只用 LLM 复核
  （失败默认放行，宁缺勿滥）——分路逻辑见 agent/nodes.py › node_compliance。
"""
from __future__ import annotations

from dataclasses import dataclass

from src.utils.embedding import hash_embed, cosine

# 违规话术样本库（语义锚点）：换皮表达会与这些句子向量相近
VIOLATION_EXEMPLARS: list[str] = [
    "这款产品保证本金安全利息确定",
    "不管你征信多差都可以放款",
    "百分之百一定能批下来",
    "黑户白户统统可以做",
    "保证所有人都能通过审批",
    "借钱给你稳赚不赔",
    "我们有银行内部的关系可以操作",
    "完全不需要任何费用利息全免",
    "想借多少就借多少没有限制",
]

DEFAULT_THRESHOLD = 0.55  # 哈希伪 embedding 下的经验阈值（见 implementation-guide 4.2）


@dataclass
class SemanticHit:
    exemplar: str
    similarity: float


@dataclass
class SemanticVerdict:
    passed: bool
    hits: list[SemanticHit]
    method: str  # "hash-embedding" / "llm" / "skipped"


def check_semantic(
    text: str,
    threshold: float = DEFAULT_THRESHOLD,
    dim: int = 256,
    llm=None,
    use_vector: bool = True,
) -> SemanticVerdict:
    """语义审核主入口。返回命中详情，便于 demo 展示与审计留痕。

    use_vector=False 时跳过伪向量比对（对话回复在真实 LLM 模式下只用
    LLM 复核——伪向量锚定的是“违规营销话术”，对顾问式对话误伤面大，
    仅在完全无 LLM 的离线 demo 中作为唯一语义层启用）。
    LLM 复核失败默认放行（对话场景宁缺勿滥），调用方经 tracer 留痕。
    """
    # 1) 向量相似度（可选；离线 demo 的兜底手段）
    hits: list[SemanticHit] = []
    method = "skipped"
    if use_vector:
        vec = hash_embed(text, dim=dim)
        hits = [
            SemanticHit(exemplar=ex, similarity=round(cosine(vec, hash_embed(ex, dim=dim)), 4))
            for ex in VIOLATION_EXEMPLARS
        ]
        hits = [h for h in hits if h.similarity >= threshold]
        hits.sort(key=lambda h: h.similarity, reverse=True)
        method = "hash-embedding"

    # 2) LLM 复核（可选）：向量通过但 LLM 认为违规时以 LLM 为准
    if llm is not None and not getattr(llm, "is_mock", False) and not hits:
        try:
            if llm.review_compliance(text) is False:
                hits.append(SemanticHit(exemplar="LLM复核判定违规", similarity=1.0))
                method = "llm"
        except Exception:
            pass  # LLM 故障不影响主链路，默认放行

    return SemanticVerdict(passed=not hits, hits=hits, method=method)
