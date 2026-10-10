"""分层记忆管理器：短期( Redis ) + 长期( PGVector ) 的统一门面。

写入策略（write_turn）：
1. 原始消息追加进短期记忆（滑动窗口）；
2. 同时从用户消息中【规则抽取】结构化事实，upsert 进长期记忆；
   （真实环境可换 LLM 抽取，见 implementation-guide 5.3 的调优要点）

读取策略（read_context）：
- 短期：直接取最近会话窗口（保对话连贯）；
- 长期：以“当前 query + 短期摘要”做语义召回（跨会话个性化）；
- 两者融合为 MemoryContext 交给下游节点。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.memory.pgvector_memory import LongTermMemory, Fact
from src.memory.redis_memory import ShortTermMemory
from src.recommend.slots import extract_slots_rules, SlotSet

# 槽位 → 事实键 的映射：决定哪些槽位值得长期留存
_FACT_KEY_MAP = {
    "monthly_income": "月收入",
    "purpose": "借款用途",
    "amount": "意向额度",
    "term_months": "意向期限",
    "occupation": "职业身份",
    "credit_status": "征信情况",
    "age": "年龄",
}


@dataclass
class MemoryContext:
    history_text: str = ""
    history_len: int = 0
    facts: list[Fact] = field(default_factory=list)
    inherited_slots: SlotSet = field(default_factory=SlotSet)

    def facts_text(self) -> str:
        if not self.facts:
            return "（无长期记忆）"
        return "；".join(f"{f.fact_key}={f.fact_value}" for f in self.facts)


class MemoryManager:
    """分层记忆统一入口。"""

    def __init__(
        self,
        short: ShortTermMemory | None = None,
        long: LongTermMemory | None = None,
        fact_top_k: int = 5,
    ) -> None:
        self.short = short or ShortTermMemory()
        self.long = long or LongTermMemory()
        self.fact_top_k = fact_top_k

    # ------------------------------------------------------------------ 写

    def extract_facts(self, user_text: str) -> dict[str, str]:
        """从用户话语中抽取可留存事实（规则版；返回 事实键→值）。"""
        slots = extract_slots_rules(user_text)
        facts: dict[str, str] = {}
        data = slots.filled()
        for slot_key, fact_name in _FACT_KEY_MAP.items():
            value = data.get(slot_key)
            if value is None:
                continue
            if slot_key == "amount":
                facts[fact_name] = f"{value / 10000:g}万"
            elif slot_key == "monthly_income":
                facts[fact_name] = f"{value:g}元/月"
            elif slot_key == "term_months":
                facts[fact_name] = f"{value}个月"
            elif slot_key == "age":
                facts[fact_name] = f"{value}岁"
            else:
                facts[fact_name] = str(value)
        return facts

    def write_turn(self, user_id: str, session_id: str,
                   user_text: str, assistant_text: str,
                   extract_facts: bool = True) -> dict[str, str]:
        """一轮对话落记忆，返回本轮新写入的长期事实（供展示/日志）。

        extract_facts=False 时只写短期窗口，不做长期事实抽取
        （用于咨询/闲聊等不该产生事实的轮次，防止噪声入库）。
        """
        self.short.append(session_id, "user", user_text)
        self.short.append(session_id, "assistant", assistant_text)
        facts = self.extract_facts(user_text) if extract_facts else {}
        for key, value in facts.items():
            self.long.upsert_fact(user_id, key, value)
        return facts

    # ------------------------------------------------------------------ 读

    def read_context(self, user_id: str, session_id: str, query: str) -> MemoryContext:
        """融合读取：短期窗口 + 长期事实召回 + 从历史继承的槽位。"""
        history = self.short.get_history(session_id)
        history_text = "\n".join(f"{m.role}: {m.content}" for m in history[-6:])
        facts = self.long.search_facts(user_id, query or "贷款", top_k=self.fact_top_k)

        # 槽位继承：从最近几轮“用户原话”里补抽取，解决“那20万呢”这类指代
        inherited = SlotSet()
        for m in history[-6:]:
            if m.role == "user":
                inherited = inherited.merge(extract_slots_rules(m.content))
        return MemoryContext(
            history_text=history_text,
            history_len=len(history),
            facts=facts,
            inherited_slots=inherited,
        )
