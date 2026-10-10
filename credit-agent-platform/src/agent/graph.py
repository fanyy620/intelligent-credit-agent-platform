"""LangGraph 主流程编排。

流程：memory_read → route_intent → 按意图分支（咨询/利率/推荐/文案/闲聊/人工）
      → compliance（双重风控出口把关）→ memory_write。

langgraph 可用时构建真正的 StateGraph（条件边路由）；不可用时降级为
顺序流水线 —— 两者共享 nodes.py 中的同一套节点函数，行为一致。
"""
from __future__ import annotations

import os

from src.agent.state import AgentState, initial_state
from src.agent import nodes
from src.agent.nodes import RuntimeContext
from src.intent.lora_router import build_router
from src.memory.experience import ExperienceStore
from src.memory.manager import MemoryManager
from src.memory.pgvector_memory import LongTermMemory
from src.memory.redis_memory import ShortTermMemory
from src.observability.tracing import get_tracer
from src.recommend.catalog import get_catalog
from src.recommend.rerank import CatalogStats, RankWeights

# 意图 → 业务节点 的分发表
_DISPATCH = {
    "PRODUCT_CONSULT": nodes.node_consult,
    "RATE_QUERY": nodes.node_rate_query,
    "CREDIT_RECOMMEND": nodes.node_recommend,
    "LIMIT_QUERY": nodes.node_recommend,      # 额度问题本质也是“我能贷多少”
    "APPLY_PROCESS": nodes.node_consult,      # 教学简化：流程问题落到产品总览
    "REPAYMENT": nodes.node_consult,
    "MATERIALS": nodes.node_consult,
    "COPYWRITING": nodes.node_copywriting,
    "CHITCHAT": nodes.node_chitchat,
    "HUMAN_AGENT": nodes.node_human,
}


# ------------------------------------------------------------------ 装配

def build_context(settings=None) -> RuntimeContext:
    """装配运行时依赖：任何外部服务不可用都自动降级，保证可运行。"""
    if settings is None:
        from configs.settings import get_settings

        settings = get_settings()

    from src.llm.client import get_llm

    llm = get_llm(settings)
    router = build_router(settings, llm)
    catalog = get_catalog(settings.products_yaml)
    memory = MemoryManager(
        short=ShortTermMemory(redis_url=settings.redis_url,
                              ttl_seconds=settings.session_ttl_seconds,
                              window=settings.session_window),
        long=LongTermMemory(database_url=settings.database_url, dim=settings.embedding_dim),
        fact_top_k=settings.memory_fact_top_k,
    )
    return RuntimeContext(
        llm=llm,
        router=router,
        memory=memory,
        catalog=catalog,
        stats=CatalogStats.from_catalog(catalog),
        weights=RankWeights(
            amount=settings.weight_amount, term=settings.weight_term,
            rate=settings.weight_rate, speed=settings.weight_speed,
            semantic=settings.semantic_weight,
        ),
        tracer=get_tracer(settings),
        embedding_dim=settings.embedding_dim,
        # 辩论层开关：settings 仅支持 str/int/float 字段，布尔开关直接读 env
        # （DEBATE_ENABLED=0/false/off 关闭，默认开；延迟敏感场景可一键降级）
        debate_enabled=os.getenv("DEBATE_ENABLED", "1").lower() not in ("0", "false", "off"),
        experience_store=ExperienceStore(),
    )


# ------------------------------------------------------------------ 执行

def _sequential_run(state: AgentState, ctx: RuntimeContext) -> AgentState:
    """无 langgraph 降级路径：按固定拓扑顺序执行节点。"""
    state.update(nodes.node_memory_read(state, ctx))
    state.update(nodes.node_route_intent(state, ctx))
    handler = _DISPATCH.get(state["intent"], nodes.node_chitchat)
    state.update(handler(state, ctx))
    state.update(nodes.node_compliance(state, ctx) or {})
    state.update(nodes.node_memory_write(state, ctx))
    return state


def _build_langgraph(ctx: RuntimeContext):
    """langgraph 可用时构建 StateGraph；任何一步失败返回 None。"""
    try:
        from langgraph.graph import END, StateGraph  # type: ignore
    except ImportError:
        return None

    def wrap(fn):
        return lambda s: fn(s, ctx)

    g = StateGraph(AgentState)
    g.add_node("memory_read", wrap(nodes.node_memory_read))
    g.add_node("route_intent", wrap(nodes.node_route_intent))
    for name, fn in {
        "consult": nodes.node_consult,
        "rate_query": nodes.node_rate_query,
        "recommend": nodes.node_recommend,
        "copywriting": nodes.node_copywriting,
        "chitchat": nodes.node_chitchat,
        "human": nodes.node_human,
    }.items():
        g.add_node(name, wrap(fn))
    g.add_node("compliance", wrap(nodes.node_compliance))
    g.add_node("memory_write", wrap(nodes.node_memory_write))

    g.set_entry_point("memory_read")
    g.add_edge("memory_read", "route_intent")
    g.add_conditional_edges(
        "route_intent",
        lambda s: {
            "PRODUCT_CONSULT": "consult", "RATE_QUERY": "rate_query",
            "CREDIT_RECOMMEND": "recommend", "LIMIT_QUERY": "recommend",
            "COPYWRITING": "copywriting", "HUMAN_AGENT": "human",
        }.get(s["intent"], "chitchat"),
    )
    for name in ("consult", "rate_query", "recommend", "copywriting", "chitchat", "human"):
        g.add_edge(name, "compliance")
    g.add_edge("compliance", "memory_write")
    g.add_edge("memory_write", END)
    return g.compile()


def run_turn(user_input: str, user_id: str, session_id: str,
             ctx: RuntimeContext, use_langgraph: bool = True) -> AgentState:
    """单轮对话主入口。"""
    state = initial_state(user_id=user_id, session_id=session_id, user_input=user_input)
    graph = _build_langgraph(ctx) if use_langgraph else None
    if graph is not None:
        return graph.invoke(state)
    return _sequential_run(state, ctx)
