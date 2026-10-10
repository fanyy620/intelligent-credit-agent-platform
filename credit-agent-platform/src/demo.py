"""端到端命令行 demo：多轮对话演示 三层推荐 + 分层记忆 + 双重风控。

零外部服务可运行：LLM→MockLLM，Redis→内存TTL，PGVector→内存向量库，
Langfuse→内存 trace 缓冲。有真实服务时（配置 .env）同一套代码自动升级。

运行：python src/demo.py    或    python -m src.demo
"""
from __future__ import annotations

import sys
from pathlib import Path

# 以脚本方式运行时，把项目根目录加入 sys.path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

from configs.settings import get_settings                     # noqa: E402
from src.agent.graph import build_context, run_turn           # noqa: E402
from src.compliance import template_fill                      # noqa: E402

DIV = "=" * 72
SUB = "-" * 72

# 教学剧本：一位客户经理与助手围绕“装修贷”的四轮交互
SCRIPT = [
    "你好，我想了解一下你们的消费贷款产品，都有哪几种？",
    "我月收入1万5，想借20万装修房子，3年内还清，征信良好，帮我推荐一下",
    "挺好的，那帮我针对这款产品写一段朋友圈推广文案",
    "把刚才的文案改成：本产品保本保息，百分百下款，无视黑白户也能下款",
]


def _print_recommend_layers(state: dict) -> None:
    """打印三层推荐架构的中间结果。"""
    print(f"[槽位抽取] {state['slots']}")

    print("[第一层·规则硬过滤]")
    for c in state["recall"]:
        p = c.product
        if c.rule_passed:
            print(f"    通过  {p.name}")
        else:
            print(f"    拒绝  {p.name:<8} 原因: {c.rule_reasons[0] if c.rule_reasons else ''}")

    passed = [c for c in state["recall"] if c.rule_passed]
    top = sorted(passed, key=lambda c: c.semantic_score, reverse=True)[:3]
    print("[第二层·RAG语义召回] (伪embedding余弦相似度，Top3)")
    for c in top:
        print(f"    {c.product.name:<8} 语义分 {c.semantic_score:.4f}")

    print("[第三层·业务评分重排] final = 0.75*业务分 + 0.25*语义分")
    print(f"    {'产品':<8}{'额度':>6}{'利率':>6}{'期限':>6}{'速度':>6}"
          f"{'业务分':>8}{'语义分':>8}{'综合分':>8}")
    for it in state["recommendation"][:3]:
        print(f"    {it.candidate.product.name:<8}"
              f"{it.amount_score:>6.2f}{it.rate_score:>6.2f}"
              f"{it.term_score:>6.2f}{it.speed_score:>6.2f}"
              f"{it.business_score:>8.3f}{it.candidate.semantic_score:>8.3f}"
              f"{it.final_score:>8.3f}")
        if it.llm_reason:
            print(f"        LLM推荐理由: {it.llm_reason}")


def _print_compliance(state: dict) -> None:
    sem = state.get("compliance_semantic") or {}
    if state.get("blocked"):
        print("[合规审核·双重风控] 拦截！")
        for v in state.get("compliance_regex", []):
            print(f"    正则命中「{v['rule_name']}」: “{v['matched']}”")
        for h in sem.get("hits", [])[:3]:
            print(f"    语义命中: “{h['exemplar']}” 相似度 {h['similarity']}")
    else:
        hits = len(state.get("compliance_regex", []))
        print(f"[合规审核·双重风控] 通过 (正则命中{hits}条, 语义审核{sem.get('method', '-')}: 通过)")


def main() -> int:
    settings = get_settings()
    ctx = build_context(settings)
    llm_kind = "MockLLM(无API Key，内置确定性应答)" if getattr(ctx.llm, "is_mock", False) \
        else f"{getattr(ctx.llm, 'backend_name', 'llm')}({getattr(ctx.llm, 'model_name', '') or 'unknown'})"

    print(DIV)
    print("  智能信贷营销与咨询一体化 Agent 平台 · 端到端演示")
    print(DIV)
    print(f"运行环境: LLM={llm_kind}")
    print(f"          短期记忆={ctx.memory.short.backend_name}  "
          f"长期记忆={ctx.memory.long.backend_name}  "
          f"Langfuse={'on' if type(ctx.tracer).__name__ == 'LangfuseTracer' else 'off(内存trace)'}")
    print(f"          产品库={len(ctx.catalog)}个  意图路由=LoRA优先(降级自动回退Prompt)")
    print(DIV)

    user_id, session_id = "u-demo-001", "s-demo-001"
    for turn, text in enumerate(SCRIPT, 1):
        print(f"\n{'#' * 20} 第 {turn} 轮 {'#' * 20}")
        print(f"客户: {text}")
        print(SUB)

        state = run_turn(text, user_id=user_id, session_id=session_id, ctx=ctx,
                         use_langgraph=True)

        mem = state["memory_context"]
        print(f"[意图路由] {state['intent']} {state['intent_zh']} "
              f"(backend={state['intent_backend']}; {state['intent_detail']})")
        print(f"[记忆读取] 短期{mem.history_len}条 | 长期事实: {mem.facts_text()}")
        if mem.inherited_slots.filled():
            print(f"[槽位继承] 从历史会话继承: {mem.inherited_slots.filled()}")

        if state["intent"] in ("CREDIT_RECOMMEND", "LIMIT_QUERY"):
            _print_recommend_layers(state)
        if state.get("copy_text"):
            print(f"[文案生成] 来源={state['copy_source']}")
            if state.get("copy_template"):
                print(f"    LLM输出模板: {state['copy_template']}")
        _print_compliance(state)

        print(SUB)
        print("助手:")
        for line in state["answer"].splitlines():
            print(f"  {line}")
        print(f"[记忆写入] 新增长期事实: {state.get('memory_facts_written') or '无'}")

    # ---------------------------------------------------------- 收尾展示
    print(f"\n{DIV}")
    print("  演示收尾：跨会话长期记忆 / 离线 trace / 数值幻觉对照")
    print(DIV)
    print("[长期事实记忆全量] （下次会话开场即可被语义召回，实现“我记得这位客户”）")
    for f in ctx.memory.long.all_facts(user_id):
        print(f"    {f.fact_key} = {f.fact_value}")

    print("\n[离线 trace 摘要] （配置 LANGFUSE_* 后自动上报为全链路追踪）")
    print(ctx.tracer.summary())

    top1_product = max(ctx.catalog, key=lambda p: p.max_amount)  # 兜底展示用
    rec_facts = {f.fact_key: f.fact_value for f in ctx.memory.long.all_facts(user_id)}
    named = rec_facts.get("最近推荐产品")
    if named:
        top1_product = next((p for p in ctx.catalog if p.name == named), top1_product)
    print("\n[营销文案数值幻觉对照实验]")
    print(template_fill.hallucination_contrast_demo(top1_product))
    print(f"\n{DIV}\n演示结束。\n{DIV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
