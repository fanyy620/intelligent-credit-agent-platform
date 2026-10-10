"""LoRA 微调意图路由（增强方案）。

用 LLaMA-Factory 在 1000 条业务对话数据上对 Qwen2.5-1.5B-Instruct 做
LoRA SFT（配置见 training/llama_factory/intent_lora_sft.yaml），
合并导出后用 transformers 本地加载做意图分类。

教学复盘指标：Prompt 基线约 70% 准确率 → LoRA 方案 85%+。

降级设计（本文件的关键纪律）：
- transformers / torch 未安装、模型目录不存在、加载抛错 ——
  任何一种情况都自动回退到 PromptIntentRouter，并在 RouteResult.backend
  中标记 "prompt_fallback"，保证系统永远可用；
- 模型加载是惰性的（首次 route 时才加载），避免拖慢启动。
"""
from __future__ import annotations

import re
from pathlib import Path

from src.intent.labels import CODE_TO_LABEL
from src.intent.prompt_router import PromptIntentRouter, RouteResult

_LABEL_CODES = list(CODE_TO_LABEL)


class LoraIntentRouter:
    """LoRA 微调模型路由；不可用时透明降级到 Prompt 路由。"""

    name = "lora"

    def __init__(self, model_path: str, fallback: PromptIntentRouter) -> None:
        self.model_path = model_path
        self.fallback = fallback
        self._model = None
        self._tokenizer = None
        self._load_error: str | None = None
        self._loaded = False

    # ------------------------------------------------------------- 加载

    def _try_load(self) -> bool:
        """惰性加载模型；任何失败都记录原因并返回 False。"""
        if self._loaded:
            return self._model is not None
        self._loaded = True
        path = Path(self.model_path)
        if not path.exists():
            self._load_error = f"模型目录不存在: {path}"
            return False
        try:
            import torch  # type: ignore  # noqa: F401
            from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore

            self._tokenizer = AutoTokenizer.from_pretrained(str(path))
            self._model = AutoModelForCausalLM.from_pretrained(
                str(path), torch_dtype="auto", device_map="auto"
            )
            self._model.eval()
            return True
        except Exception as e:  # 缺包/缺权重/显存不足，统一降级
            self._load_error = f"{type(e).__name__}: {e}"
            self._model = None
            return False

    # ------------------------------------------------------------- 推理

    def _infer(self, text: str) -> str | None:
        prompt = (
            "你是银行信贷助手的意图分类器，请判断用户问题的意图，只输出意图标签编码。\n"
            f"用户：{text}\n意图："
        )
        inputs = self._tokenizer(prompt, return_tensors="pt").to(self._model.device)
        import torch  # type: ignore

        with torch.no_grad():
            out = self._model.generate(**inputs, max_new_tokens=16, do_sample=False)
        decoded = self._tokenizer.decode(out[0][inputs["input_ids"].shape[1]:],
                                         skip_special_tokens=True)
        m = re.search(r"[A-Z_]{3,}", decoded)
        return m.group(0) if m else None

    # ------------------------------------------------------------- 路由

    def route(self, text: str) -> RouteResult:
        if self._try_load():
            try:
                code = self._infer(text)
                if code in CODE_TO_LABEL:
                    return RouteResult(code=code, zh=CODE_TO_LABEL[code].zh,
                                       backend="lora", detail="lora 微调模型直出")
            except Exception:
                pass  # 单次推理失败同样走兜底
        result = self.fallback.route(text)
        result.backend = "prompt_fallback"
        if self._load_error:
            result.detail += f"；LoRA 不可用（{self._load_error}），已降级 Prompt 路由"
        return result


def build_router(settings=None, llm=None) -> PromptIntentRouter | LoraIntentRouter:
    """路由工厂：优先 LoRA（内部自带降级），返回统一接口。"""
    if settings is None:
        from configs.settings import get_settings

        settings = get_settings()
    if llm is None:
        from src.llm.client import get_llm

        llm = get_llm(settings)
    prompt_router = PromptIntentRouter(llm)
    return LoraIntentRouter(model_path=settings.intent_model_path, fallback=prompt_router)
