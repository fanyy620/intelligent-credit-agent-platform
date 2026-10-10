"""Langfuse 全链路可观测。

监控对象：意图识别、记忆检索、工具调用、大模型推理，以及每一步的
时延 / Token / 关键属性（如意图标签、召回条数、合规命中）。

设计：
- Tracer 提供 trace/span/event 三级 API，全部实现为上下文管理器，
  业务代码零侵入；
- 未配置 LANGFUSE_* 或缺少 langfuse 包时返回 NoopTracer —— 不报错、
  不阻塞，但保留内存缓冲，demo 可打印“离线 trace 摘要”；
- 配置完整时自动升级为 LangfuseTracer，把 span 同步上报。
"""
from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass
class SpanRecord:
    name: str
    start: float
    end: float = 0.0
    attrs: dict = field(default_factory=dict)

    @property
    def latency_ms(self) -> float:
        if not self.end:
            return 0.0
        return (self.end - self.start) * 1000


class NoopTracer:
    """无外部依赖的 Tracer：什么都不上报，仅内存留痕（可关闭）。"""

    def __init__(self, keep_buffer: bool = True, service: str = "credit-agent") -> None:
        self.keep_buffer = keep_buffer
        self.service = service
        self.records: list[SpanRecord] = []
        self.trace_id = uuid.uuid4().hex[:16]

    @contextmanager
    def span(self, name: str, **attrs):
        rec = SpanRecord(name=name, start=time.perf_counter(), attrs=dict(attrs))
        try:
            yield rec
        finally:
            rec.end = time.perf_counter()
            if self.keep_buffer:
                self.records.append(rec)

    def event(self, name: str, **attrs) -> None:
        if self.keep_buffer:
            now = time.perf_counter()
            self.records.append(SpanRecord(name=name, start=now, end=now, attrs=dict(attrs)))

    def summary(self) -> str:
        """离线 trace 摘要（demo 结尾打印，模拟 Langfuse 看板内容）。"""
        if not self.records:
            return "（无 trace 记录）"
        lines = [f"trace_id={self.trace_id} service={self.service}"]
        total = 0.0
        for r in self.records:
            ms = r.latency_ms
            total += ms
            attr = " ".join(f"{k}={v}" for k, v in r.attrs.items())
            lines.append(f"  - {r.name:<22} {ms:8.2f} ms  {attr}")
        lines.append(f"  合计 {total:.2f} ms（{len(self.records)} 个 span）")
        return "\n".join(lines)


class LangfuseTracer(NoopTracer):
    """真实上报版：继承内存留痕，同时同步到 Langfuse。"""

    def __init__(self, public_key: str, secret_key: str, host: str, **kw) -> None:
        super().__init__(**kw)
        from langfuse import Langfuse  # type: ignore  # 延迟导入

        self._client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
        self._trace = self._client.trace(id=self.trace_id, name="credit-agent-turn")
        self._stack: list = []

    @contextmanager
    def span(self, name: str, **attrs):
        with super().span(name, **attrs) as rec:
            sp = self._trace.span(name=name, metadata=attrs)
            try:
                yield rec
            finally:
                sp.end()

    def flush(self) -> None:
        self._client.flush()


def get_tracer(settings=None, keep_buffer: bool = True) -> NoopTracer:
    """按配置返回 Tracer；任何一步失败都安全降级为 NoopTracer。"""
    try:
        if settings is None:
            from configs.settings import get_settings

            settings = get_settings()
        if settings.langfuse_public_key and settings.langfuse_secret_key:
            return LangfuseTracer(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
                keep_buffer=keep_buffer,
            )
    except Exception:
        pass
    return NoopTracer(keep_buffer=keep_buffer)
