"""Prompt 意图路由（基线方案）。

直接把标签体系写进系统提示词让 LLM 选标签。优点是零训练成本；
缺点是：1) 口语化/复合句式下不稳（教学复盘约 70% 准确率）；
2) 每次推理都要吃掉整段标签 Prompt 的 Token；
3) 模型输出格式不可控，需要解析兜底。这也是引入 LoRA 路由的动机。
"""
from __future__ import annotations

from dataclasses import dataclass

from src.intent.labels import CODE_TO_LABEL, ALL_INTENTS


@dataclass
class RouteResult:
    code: str
    zh: str
    backend: str        # "prompt" / "lora" / "prompt_fallback"
    detail: str = ""

    def to_dict(self) -> dict:
        return {"code": self.code, "zh": self.zh, "backend": self.backend, "detail": self.detail}


class PromptIntentRouter:
    """基线：LLM + Prompt 路由。MockLLM 下退化为关键词评分。"""

    name = "prompt"

    def __init__(self, llm) -> None:
        self.llm = llm

    def route(self, text: str) -> RouteResult:
        code, detail = self.llm.classify_intent(text)
        label = CODE_TO_LABEL.get(code)
        if label is None:
            label = next(i for i in ALL_INTENTS if i.code == "CHITCHAT")
            detail += "；非法标签兜底为闲聊"
        return RouteResult(code=label.code, zh=label.zh, backend="prompt", detail=detail)
