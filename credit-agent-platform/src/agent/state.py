"""LangGraph AgentState 定义。

使用 TypedDict（total=False）：既是 LangGraph 的原生状态类型，
又是普通 dict —— 无 langgraph 时顺序流水线同样操作它，零依赖。
"""
from __future__ import annotations

import time
import uuid
from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # ---- 输入 ----
    user_id: str
    session_id: str
    user_input: str
    trace_id: str
    ts: float

    # ---- 意图 ----
    intent: str           # 意图编码（IntentLabel.code）
    intent_zh: str        # 中文名
    intent_backend: str   # prompt / lora / prompt_fallback
    intent_detail: str

    # ---- 记忆 ----
    memory_context: Any   # MemoryContext
    memory_facts_written: dict[str, str]

    # ---- 推荐 ----
    slots: dict[str, Any]            # 合并后的槽位
    recall: list[Any]                # 两层召回结果（Candidate，含拒绝项）
    recommendation: list[Any]        # 重排结果（RankedItem）
    debate: dict | None              # 双视角辩论裁决（DebateResult.to_dict()，未触发为 None）

    # ---- 营销文案 ----
    copy_template: str
    copy_text: str
    copy_source: str                 # "template_fill" / "user_draft"

    # ---- 合规 ----
    compliance_regex: list[dict]     # regex_guard 命中
    compliance_semantic: dict        # semantic_guard 结论
    blocked: bool

    # ---- 输出 ----
    answer: str


def initial_state(user_id: str, session_id: str, user_input: str) -> AgentState:
    return AgentState(
        user_id=user_id,
        session_id=session_id,
        user_input=user_input,
        trace_id=uuid.uuid4().hex[:16],
        ts=time.time(),
        intent="",
        intent_zh="",
        intent_backend="",
        intent_detail="",
        slots={},
        recall=[],
        recommendation=[],
        compliance_regex=[],
        compliance_semantic={},
        blocked=False,
        answer="",
    )
