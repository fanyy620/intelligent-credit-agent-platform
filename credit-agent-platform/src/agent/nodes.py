"""LangGraph 节点函数。

每个节点都是纯函数 (state, ctx) -> partial_state，不依赖 langgraph，
因此顺序流水线（无依赖降级路径）与 LangGraph 图共享同一套节点实现。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.agent.state import AgentState
from src.compliance import regex_guard, semantic_guard, template_fill
from src.debate import run_debate
from src.memory.manager import MemoryManager
from src.recommend.catalog import Product
from src.recommend.recall import recall_two_stage
from src.recommend.rerank import CatalogStats, RankWeights, rerank
from src.recommend.slots import SlotSet, extract_slots


@dataclass
class RuntimeContext:
    """节点共享的运行时依赖（在 graph.py 中装配）。"""

    llm: object
    router: object
    memory: MemoryManager
    catalog: list[Product]
    stats: CatalogStats
    weights: RankWeights
    tracer: object
    embedding_dim: int = 256
    debate_enabled: bool = True          # DEBATE_ENABLED env 可关闭（延迟敏感场景）
    experience_store: object = None      # 推荐经验库（ExperienceStore，None=不启用）


# ------------------------------------------------------------------ 记忆节点

def node_memory_read(state: AgentState, ctx: RuntimeContext) -> dict:
    """读取分层记忆：短期窗口 + 长期事实召回。"""
    with ctx.tracer.span("memory.read", backend=f"{ctx.memory.short.backend_name}+{ctx.memory.long.backend_name}"):
        mem = ctx.memory.read_context(state["user_id"], state["session_id"], state["user_input"])
    ctx.tracer.event("memory.read.done", history_len=mem.history_len,
                     facts=len(mem.facts), facts_text=mem.facts_text())
    return {"memory_context": mem}


def node_memory_write(state: AgentState, ctx: RuntimeContext) -> dict:
    """本轮对话落记忆：短期追加 + 长期事实抽取 upsert。"""
    with ctx.tracer.span("memory.write"):
        # 事实抽取只在推荐类意图下启用：咨询/闲聊中的品类词（如“消费贷”）
        # 会产生噪声事实（把“想了解消费贷”误存为“借款用途=消费”）
        extract = state.get("intent") in ("CREDIT_RECOMMEND", "LIMIT_QUERY")
        facts = ctx.memory.write_turn(
            state["user_id"], state["session_id"],
            state["user_input"], state["answer"],
            extract_facts=extract,
        )
        # 若本轮产生了推荐结果，把 Top1 产品名写入长期事实，
        # 使下一轮“针对这款产品生成文案”这类指代可以跨轮解析
        if state.get("recommendation"):
            top1 = state["recommendation"][0].candidate.product.name
            ctx.memory.long.upsert_fact(state["user_id"], "最近推荐产品", top1)
            facts = {**facts, "最近推荐产品": top1}
            # 高分且未被合规拦截的推荐沉淀为经验条目（中金"因子库经验记忆"映射）
            if ctx.experience_store is not None:
                exp = ctx.experience_store.maybe_save(
                    state["recommendation"], state.get("slots") or {},
                    state["session_id"], blocked=state.get("blocked", False))
                if exp is not None:
                    ctx.tracer.event("experience.saved", product=exp.product_name,
                                     final_score=exp.final_score)
    ctx.tracer.event("memory.write.done", new_facts=facts)
    return {"memory_facts_written": facts}


# ------------------------------------------------------------------ 意图节点

def node_route_intent(state: AgentState, ctx: RuntimeContext) -> dict:
    """意图路由：LoRA 优先，自动降级 Prompt。"""
    with ctx.tracer.span("intent.route") as span:
        result = ctx.router.route(state["user_input"])
        span.attrs["intent"] = result.code
        span.attrs["backend"] = result.backend
    return {
        "intent": result.code,
        "intent_zh": result.zh,
        "intent_backend": result.backend,
        "intent_detail": result.detail,
    }


# ------------------------------------------------------------------ 业务节点

def _find_products_by_text(ctx: RuntimeContext, text: str) -> list[Product]:
    """按产品名/类别关键词在产品库中查找。"""
    hits = [p for p in ctx.catalog if p.name in text or p.category in text]
    return hits


def node_consult(state: AgentState, ctx: RuntimeContext) -> dict:
    """产品咨询：给出产品总览（数值全部来自结构化目录）。"""
    with ctx.tracer.span("node.consult"):
        hits = _find_products_by_text(ctx, state["user_input"])
        products = hits if hits else ctx.catalog
        lines = ["我们目前在售的信贷产品如下，您可以告诉我您的资金用途和金额，我帮您精准匹配："]
        for p in products[:6]:
            lines.append(f"  - {p.summary()}")
        answer = "\n".join(lines)
    return {"answer": answer}


def node_rate_query(state: AgentState, ctx: RuntimeContext) -> dict:
    """利率查询：数值直接引用结构化字段，杜绝报价幻觉。"""
    with ctx.tracer.span("node.rate_query"):
        hits = _find_products_by_text(ctx, state["user_input"])
        if hits:
            lines = ["为您查到以下产品的利率信息："]
            for p in hits:
                lines.append(
                    f"  - {p.name}：年化利率 {p.rate_range_pct}（单利），"
                    f"具体以审批结果为准"
                )
        else:
            lo = min(p.annual_rate_min for p in ctx.catalog)
            hi = max(p.annual_rate_max for p in ctx.catalog)
            lines = [
                f"我行信贷产品年化利率整体区间为 {lo * 100:g}%-{hi * 100:g}%（单利）。"
                "告诉我具体产品名，我可以给出更精确的区间。"
            ]
        answer = "\n".join(lines)
    return {"answer": answer}


def node_recommend(state: AgentState, ctx: RuntimeContext) -> dict:
    """授信推荐：槽位抽取 → 规则+RAG召回 → 业务评分重排（三层架构主干）。

    重排之后、回复生成之前插入两道中金方法论机制：
    经验库检索（相似历史推荐注入上下文）+ 双视角辩论（风险提示/Top2 再评估）。
    """
    with ctx.tracer.span("slots.extract", channel="rules+llm"):
        current = extract_slots(state["user_input"], llm=ctx.llm)
        inherited = state["memory_context"].inherited_slots if state.get("memory_context") else SlotSet()
        slots = inherited.merge(current)  # 本轮槽位优先，历史槽位补缺
    ctx.tracer.event("slots.extract.done", slots=slots.filled())

    with ctx.tracer.span("recall.two_stage"):
        candidates = recall_two_stage(ctx.catalog, slots, raw_text=state["user_input"],
                                      dim=ctx.embedding_dim)
        passed = [c for c in candidates if c.rule_passed]
    ctx.tracer.event("recall.done", total=len(ctx.catalog), passed=len(passed))

    with ctx.tracer.span("rerank.business"):
        ranked = rerank(candidates, slots, ctx.stats, ctx.weights,
                        llm=ctx.llm, use_llm=True)

    # ---- 经验库检索（中金"因子库经验记忆"映射：历史优质推荐注入本轮上下文）----
    experiences: list = []
    if ctx.experience_store is not None and ranked:
        with ctx.tracer.span("experience.recall"):
            experiences = ctx.experience_store.search_similar(
                slots.filled(), top_k=2, exclude_session=state["session_id"])
    ctx.tracer.event("experience.recall.done", hits=len(experiences))

    # ---- 双视角辩论（中金 Multi-Agent 方法论映射：重排之后、回复之前）----
    debate = None
    if ranked and ctx.debate_enabled:
        with ctx.tracer.span("debate.dual_perspective"):
            debate = run_debate(
                ranked, slots.filled(),
                facts=state["memory_context"].facts if state.get("memory_context") else [],
                experiences=experiences, llm=ctx.llm, tracer=ctx.tracer)
    ctx.tracer.event("debate.done", triggered=debate is not None,
                     reevaluated=bool(debate and debate.reevaluated_top2))

    if not ranked:
        reasons = []
        for c in candidates:
            if not c.rule_passed and c.rule_reasons:
                reasons.append(f"  - {c.product.name}：{c.rule_reasons[0]}")
        answer = (
            "根据您提供的条件，暂时没有完全符合准入要求的产品。主要原因：\n"
            + "\n".join(reasons[:4])
            + "\n您可以调整金额/期限后再试，或转人工获取定制方案。"
        )
    else:
        lines = ["根据您的情况，为您推荐以下产品（按综合评分排序）："]
        for i, it in enumerate(ranked[:3], 1):
            p = it.candidate.product
            reason = it.llm_reason or "综合评分最优"
            lines.append(
                f"  Top{i} {p.name}（{p.category}）综合分 {it.final_score:.3f}\n"
                f"      额度{p.min_amount / 10000:g}-{p.max_amount_wan}，"
                f"年化{p.rate_range_pct}，{p.min_term_months}-{p.max_term_months}个月，"
                f"最快{p.approval_hours:g}小时审批\n"
                f"      推荐理由：{reason}"
            )
        lines.append("以上额度和利率均以最终审批为准。")
        # 辩论裁决落回复：风险提示分区 + Top2 再评估说明（"提质"的用户可见形态）
        if debate and debate.risk_notice:
            lines.append("风险提示：")
            for notice in debate.risk_notice[:3]:
                lines.append(f"  - {notice}")
        if debate and debate.top2_note:
            lines.append(debate.top2_note)
        answer = "\n".join(lines)

    return {"slots": slots.filled(), "recall": candidates,
            "recommendation": ranked,
            "debate": debate.to_dict() if debate else None,
            "answer": answer}


def _extract_user_draft(text: str) -> str | None:
    """识别“把文案改成：xxx”这类用户自带稿。"""
    m = re.search(r"(?:改成|改为|换成)\s*[:：]?\s*(.+)$", text, re.S)
    if m and ("文案" in text or "话术" in text or "宣传" in text or "朋友圈" in text):
        return m.group(1).strip().strip("“”\"")
    return None


def _resolve_product(state: AgentState, ctx: RuntimeContext) -> Product:
    """统一的产品解析顺序：本轮重排 Top1 → 长期记忆“最近推荐产品” →
    按输入文本中的名称匹配 → 兜底全库额度最高者。"""
    if state.get("recommendation"):
        return state["recommendation"][0].candidate.product
    if state.get("memory_context"):
        for f in state["memory_context"].facts:
            if f.fact_key == "最近推荐产品":
                hit = next((p for p in ctx.catalog if p.name == f.fact_value), None)
                if hit is not None:
                    return hit
    hits = _find_products_by_text(ctx, state["user_input"])
    if hits:
        return hits[0]
    return max(ctx.catalog, key=lambda p: p.max_amount)


def node_copywriting(state: AgentState, ctx: RuntimeContext) -> dict:
    """营销文案生成：模板+数据后填充；支持对用户自带稿做合规审查。"""
    with ctx.tracer.span("node.copywriting"):
        product = _resolve_product(state, ctx)

        draft = _extract_user_draft(state["user_input"])
        if draft is not None:
            # 用户自带稿：不渲染，直接送合规节点审查
            return {"copy_text": draft, "copy_source": "user_draft",
                    "copy_template": "", "answer": draft}

        # 正常路径：LLM 只产出无数字模板 → 代码校验 → 数据填充
        template = ctx.llm.gen_copy_template(product.name)
        free_numbers = template_fill.find_free_numbers(template)
        if free_numbers:
            # 模型越权生成了数字：拒绝渲染并换用内置安全模板（真实环境应重试/告警）
            ctx.tracer.event("copywriting.hallucination_blocked", free_numbers=free_numbers)
            template = template_fill.GOOD_LLM_TEMPLATE
        data = template_fill.product_slot_data(product)
        rendered = template_fill.render_copy(template, data)
        if not rendered.ok:
            rendered = template_fill.render_copy(template_fill.GOOD_LLM_TEMPLATE, data)
        ctx.tracer.event("copywriting.rendered", product=product.name,
                         template_slots=list(data.keys()))
        return {"copy_text": rendered.text, "copy_source": "template_fill",
                "copy_template": template, "answer": rendered.text}


def node_chitchat(state: AgentState, ctx: RuntimeContext) -> dict:
    return {"answer": "您好！我是智能信贷助手，可以帮您介绍贷款产品、查询利率、"
                      "根据您的条件推荐方案，或生成合规的营销文案。请问有什么可以帮您？"}


def node_human(state: AgentState, ctx: RuntimeContext) -> dict:
    ctx.tracer.event("handover.human", reason=state["user_input"][:50])
    return {"answer": "好的，正在为您转接人工客户经理，请稍候。"
                      "转接期间您提供的信息我会一并同步，无需重复描述。"}


# ------------------------------------------------------------------ 合规节点

def node_compliance(state: AgentState, ctx: RuntimeContext) -> dict:
    """输出前双重风控：正则硬拦截 + 语义审核，按内容类型分路。

    - 营销文案（copy_text 存在）：宁严勿宽——伪向量 + LLM 复核双闸，
      命中则围绕原产品用内置合规模板重出一版（广告投放场景，宁可误拦）；
    - 对话回复：真实 LLM 模式下只做 LLM 复核（失败默认放行，宁缺勿滥），
      伪向量仅离线 demo 启用；命中后让 LLM 按合规约束把原回复重写一版，
      仍失败才用通用安全话术——绝不替换成营销模板（答非所问）。
      策略差异的完整记录见 docs/prompt-design.md「对话回复与营销文案的合规策略差异」。
    """
    text = state.get("copy_text") or state.get("answer", "")
    if not text:
        return {}
    is_copy = bool(state.get("copy_text"))

    with ctx.tracer.span("compliance.regex"):
        violations = regex_guard.check(text)
    with ctx.tracer.span("compliance.semantic"):
        if is_copy:
            verdict = semantic_guard.check_semantic(text, llm=ctx.llm)
        else:
            verdict = semantic_guard.check_semantic(
                text, llm=ctx.llm,
                use_vector=getattr(ctx.llm, "is_mock", True))  # 伪向量仅离线 demo

    regex_hits = [v.__dict__ for v in violations]
    semantic = {"passed": verdict.passed, "method": verdict.method,
                "hits": [h.__dict__ for h in verdict.hits]}
    ctx.tracer.event("compliance.done", regex_hits=len(regex_hits),
                     semantic_passed=verdict.passed, semantic_method=verdict.method,
                     scene="copy" if is_copy else "dialogue")

    if not (violations or not verdict.passed):
        return {"compliance_regex": regex_hits, "compliance_semantic": semantic,
                "blocked": False}

    if is_copy:
        # ---- 营销文案：宁严勿宽，命中换内置合规模板重出（现状保持）----
        lines = ["[合规拦截] 该内容不符合银行营销宣传规范，未予输出："]
        for v in violations:
            lines.append(f"  - 命中规则「{v.rule_name}」：含“{v.matched}”。{v.reason}；建议：{v.suggestion}")
        for h in verdict.hits[:3]:
            lines.append(f"  - 语义审核命中：与违规样本“{h.exemplar}”相似度 {h.similarity:.2f}")
        # 给出安全替代：用模板填充方案，围绕客户原本关注的产品重出一版合规文案
        product = _resolve_product(state, ctx)
        safe = template_fill.render_copy(
            template_fill.GOOD_LLM_TEMPLATE, template_fill.product_slot_data(product)
        )
        lines.append("\n已为您改用合规模板重新生成：")
        lines.append(safe.text)
        return {"compliance_regex": regex_hits, "compliance_semantic": semantic,
                "blocked": True, "answer": "\n".join(lines)}

    # ---- 对话回复：LLM 按合规约束重写一版，失败用通用安全话术 ----
    issues = [f"{v.rule_name}（含“{v.matched}”）" for v in violations]
    issues += [f"语义审核命中（{h.exemplar}）" for h in verdict.hits[:3]]
    with ctx.tracer.span("compliance.rewrite"):
        rewritten = (ctx.llm.rewrite_compliant(text, issues=issues) or "").strip()
    ctx.tracer.event("compliance.rewrite.done", rewritten_len=len(rewritten))
    lines = ["[合规重写] 原回复未通过合规校验，以下为合规版本：", rewritten]
    return {"compliance_regex": regex_hits, "compliance_semantic": semantic,
            "blocked": True, "answer": "\n".join(lines)}
