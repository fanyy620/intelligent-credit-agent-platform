# -*- coding: utf-8 -*-
"""双视角辩论引擎（中金《Multi-Agent 如何辩论出基本面 Alpha》方法论映射）。

研报机制 → 本系统映射：
- 「质量/价值 Agent × 成长/动量 Agent」→ 「风险合规视角 × 业务增长视角」，
  围绕 Top1 推荐相互校验（提质），视角分工避免单一叙事（去同质）；
- 「评估—反馈—再生成闭环」→ 裁决逻辑：风险视角 stance=反对 或规则硬伤
  → 回复中呈现风险提示分区，并触发对 Top2 的再评估说明；
- 「机制设计 > 模型能力」→ 硬伤检测是确定性规则（可测试），模型意见只是
  输入之一；辩论层任何失败不阻塞主回复（返回 None，节点降级跳过）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

# 风险视角给出此 stance 即视为"视角硬伤"，与规则硬伤并列进入裁决
OPPOSE_STANCE = "反对"


@dataclass
class Perspective:
    """单视角意见（LLM 或离线规则模板产出，结构一致）。"""

    role: str                          # risk / growth
    stance: str                        # 支持 / 谨慎支持 / 反对
    points: list[str] = field(default_factory=list)
    suggested_caveats: list[str] = field(default_factory=list)
    score_adjust: float = 0.0

    def to_dict(self) -> dict:
        return {"role": self.role, "stance": self.stance, "points": self.points,
                "suggested_caveats": self.suggested_caveats,
                "score_adjust": self.score_adjust}


@dataclass
class DebateResult:
    """裁决结果：两个视角意见 + 风险提示分区 + Top2 再评估说明。"""

    risk: Perspective
    growth: Perspective
    hard_issues: list[str]             # 确定性规则硬伤
    risk_notice: list[str]             # 呈现给用户的风险提示（分区文本行）
    reevaluated_top2: bool
    top2_note: str                     # Top2 再评估说明（未触发时为空）
    experiences_hint: str = ""         # 经验库命中说明

    def to_dict(self) -> dict:
        return {"risk_view": self.risk.to_dict(), "growth_view": self.growth.to_dict(),
                "hard_issues": self.hard_issues, "risk_notice": self.risk_notice,
                "reevaluated_top2": self.reevaluated_top2, "top2_note": self.top2_note,
                "experiences_hint": self.experiences_hint}


# ------------------------------------------------------------------ 硬伤规则

def detect_hard_issues(product, slots: dict) -> list[str]:
    """确定性硬伤校验（离线可跑、可测试）。

    规则过滤（recall.rule_filter）已保证"准入之内"，这里查的是准入之内
    仍然存在的偿付风险——对应中金方法论中"校验失败按错误信息自动修正"
    的 Correction 环节：校验对象是推荐结果本身，修正方式是风险提示
    + Top2 再评估，而不是人工调试。
    """
    issues: list[str] = []
    income = slots.get("monthly_income")
    amount = slots.get("amount")
    if income and amount:
        ratio = amount / max(income * 12, 1)
        if ratio > 3:
            issues.append(
                f"借款金额{amount / 10000:g}万约为客户年收入的{ratio:.1f}倍，"
                "超出常规偿债能力区间")
    return issues


def _format_experiences(pairs: list) -> str:
    """经验库命中 → 注入辩论上下文的一行式说明。"""
    if not pairs:
        return ""
    parts = [f"相似资质客户曾推荐{e.product_name}（综合分{e.final_score:.3f}，相似度{score:.2f}）"
             for e, score in pairs]
    return "；".join(parts)


def _perspective(role: str, raw: dict) -> Perspective:
    """宽容构造：LLM 返回缺键/None 时归一到安全默认，裁决不崩溃。"""
    raw = raw if isinstance(raw, dict) else {}
    try:
        adjust = float(raw.get("score_adjust") or 0.0)
    except (TypeError, ValueError):
        adjust = 0.0
    return Perspective(
        role=role,
        stance=str(raw.get("stance") or "谨慎支持"),
        points=[str(p) for p in (raw.get("points") or []) if p],
        suggested_caveats=[str(c) for c in (raw.get("suggested_caveats") or []) if c],
        score_adjust=adjust,
    )


# ------------------------------------------------------------------ 主入口

def run_debate(ranked: list, slots: dict, facts: list | None = None,
               experiences: list | None = None, llm=None,
               tracer=None) -> DebateResult | None:
    """双视角辩论主入口。

    输入：rerank 后的 RankedItem 列表（取 Top1 为评审对象）、合并槽位 dict、
    长期记忆事实、经验库相似条目、LLM 客户端。
    返回 DebateResult；任何一步失败返回 None（调用方降级跳过，主回复不受阻）。
    """
    if not ranked or llm is None:
        return None
    top1 = ranked[0].candidate.product
    facts_text = "；".join(f.text() for f in (facts or []))
    exp_pairs = experiences or []
    exp_text = _format_experiences(exp_pairs)

    def _event(name: str, **attrs) -> None:
        if tracer is not None:
            tracer.event(name, **attrs)

    try:
        t0 = time.perf_counter()
        risk_raw = llm.debate_perspective("risk", top1.name, slots, facts_text, exp_text)
        growth_raw = llm.debate_perspective("growth", top1.name, slots, facts_text, exp_text)
        _event("debate.perspectives.done", latency_ms=round((time.perf_counter() - t0) * 1000, 1),
               risk_stance=risk_raw.get("stance"), growth_stance=growth_raw.get("stance"))
    except Exception as e:  # 辩论层整体失败 → 不阻塞主回复
        _event("debate.skipped", reason=f"{type(e).__name__}: {e}")
        return None

    risk = _perspective("risk", risk_raw)
    growth = _perspective("growth", growth_raw)

    # ---- 裁决：规则硬伤 + 视角硬伤 ----
    hard = detect_hard_issues(top1, slots)
    if risk.stance == OPPOSE_STANCE:
        reason = risk.points[0] if risk.points else "未说明具体理由"
        hard.append(f"风险合规视角反对该推荐（{reason}）")

    # ---- 风险提示分区（caveats 去重，硬伤置首）----
    notice: list[str] = list(hard)
    for c in risk.suggested_caveats:
        if c and c not in notice:
            notice.append(c)

    # ---- Top2 再评估（中金"评估—反馈—再生成"闭环的信贷映射）----
    reevaluated = bool(hard) and len(ranked) > 1
    top2_note = ""
    if reevaluated:
        top2 = ranked[1].candidate.product
        top2_note = (
            f"鉴于上述风险点，系统已对备选方案重新评估：Top2 {top2.name}"
            f"（{top2.category}，额度{top2.min_amount / 10000:g}-{top2.max_amount_wan}，"
            f"综合分{ranked[1].final_score:.3f}）或更贴合您的偿付能力，建议一并考虑。"
        )

    return DebateResult(risk=risk, growth=growth, hard_issues=hard,
                        risk_notice=notice, reevaluated_top2=reevaluated,
                        top2_note=top2_note, experiences_hint=exp_text)
