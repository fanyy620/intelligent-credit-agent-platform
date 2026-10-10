# -*- coding: utf-8 -*-
"""推荐经验库（中金"因子库经验记忆"方法论映射）。

研报做法：历史优质结果沉淀为经验库，相关性反馈注入下一轮 prompt，
提升收敛性与可复现性。本系统映射：

- 沉淀：推荐综合分超过阈值（默认 0.5）且未被合规拦截的案例，
  抽取"槽位摘要 + 推荐产品 + 评分"为经验条目；
- 反馈：下一轮推荐时按槽位相似度检索经验，注入辩论上下文
  （"相似资质客户此前推荐了X，评分Y"）；
- 降级：进程内存存储（与 memory 层的 memory-dict 降级后端同档次），
  接口预留 Redis/PG 替换点（见 implementation-guide 优化章）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

# 经验条目保留的槽位键（与推荐相关的核心画像维度）
_SUMMARY_KEYS = ("purpose", "occupation", "amount", "term_months", "monthly_income")


@dataclass
class Experience:
    """一条推荐经验：什么画像的客户 → 推荐了什么产品 → 评分多少。"""

    slots_summary: dict
    product_name: str
    final_score: float
    session_id: str
    ts: float = field(default_factory=time.time)

    def text(self) -> str:
        return f"相似资质客户曾推荐{self.product_name}（综合分{self.final_score:.3f}）"


def similarity(slots: dict, summary: dict) -> float:
    """槽位相似度（0-1，确定性、可解释）：用途 0.4 + 身份 0.3 + 金额接近 0.2 + 期限接近 0.1。"""
    score = 0.0
    if slots.get("purpose") and slots.get("purpose") == summary.get("purpose"):
        score += 0.4
    if slots.get("occupation") and slots.get("occupation") == summary.get("occupation"):
        score += 0.3
    for key, weight in (("amount", 0.2), ("term_months", 0.1)):
        a, b = slots.get(key), summary.get(key)
        if a and b:
            ratio = min(a, b) / max(a, b)  # ∈ (0,1]，越接近越高
            score += weight * ratio
    return round(score, 4)


class ExperienceStore:
    """经验库门面；默认进程内存后端，离线可用。"""

    backend_name = "memory"
    SCORE_THRESHOLD = 0.5

    def __init__(self, score_threshold: float | None = None) -> None:
        self._items: list[Experience] = []
        if score_threshold is not None:
            self.SCORE_THRESHOLD = score_threshold

    # ------------------------------------------------------------------ 写

    def maybe_save(self, ranked: list, slots: dict, session_id: str,
                   blocked: bool = False) -> Experience | None:
        """高分且未被拦截的推荐沉淀为经验；不满足条件返回 None。"""
        if blocked or not ranked:
            return None
        top = ranked[0]
        if top.final_score < self.SCORE_THRESHOLD:
            return None
        summary = {k: slots[k] for k in _SUMMARY_KEYS if slots.get(k) is not None}
        exp = Experience(slots_summary=summary,
                         product_name=top.candidate.product.name,
                         final_score=top.final_score, session_id=session_id)
        self._items.append(exp)
        return exp

    # ------------------------------------------------------------------ 读

    def search_similar(self, slots: dict, top_k: int = 2,
                       exclude_session: str | None = None,
                       min_score: float = 0.3) -> list[tuple[Experience, float]]:
        """按槽位相似度检索经验（排除本会话，防自引用回声）。"""
        scored = []
        for e in self._items:
            if exclude_session and e.session_id == exclude_session:
                continue
            s = similarity(slots, e.slots_summary)
            if s >= min_score:
                scored.append((e, s))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def __len__(self) -> int:
        return len(self._items)
