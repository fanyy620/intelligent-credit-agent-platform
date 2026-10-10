"""短期会话记忆：Redis + TTL + 滑动窗口。

分层记忆体系中的“快”层：保存当前会话最近 N 条消息，
供单轮对话内做槽位继承与指代消解。Redis 不可用时降级为
进程内 TTL 字典（接口不变，demo/测试零依赖）。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass


@dataclass
class Message:
    role: str      # "user" / "assistant"
    content: str
    ts: float = 0.0


class _InMemoryBackend:
    """Redis 的内存降级实现：key → (value, expire_ts)。"""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float]] = {}

    def _expired(self, key: str) -> bool:
        item = self._store.get(key)
        if item is None:
            return True
        if item[1] < time.time():
            self._store.pop(key, None)
            return True
        return False

    def get(self, key: str) -> str | None:
        return None if self._expired(key) else self._store[key][0]

    def set(self, key: str, value: str, ttl: int) -> None:
        self._store[key] = (value, time.time() + ttl)


class ShortTermMemory:
    """短期会话记忆（滑动窗口 + TTL）。"""

    def __init__(
        self,
        redis_url: str | None = None,
        ttl_seconds: int = 3600,
        window: int = 20,
        backend=None,
    ) -> None:
        self.ttl = ttl_seconds
        self.window = window
        self.backend_name = "memory"
        self._r = backend
        if self._r is None and redis_url:
            try:
                import redis  # type: ignore

                self._r = redis.Redis.from_url(redis_url, socket_timeout=2)
                self._r.ping()
                self.backend_name = "redis"
            except Exception:
                self._r = None
        if self._r is None:
            self._r = _InMemoryBackend()
        self._use_redis_client = self.backend_name == "redis"

    @staticmethod
    def _key(session_id: str) -> str:
        return f"credit:session:{session_id}"

    # Redis 客户端与内存后端的方法签名不同，这里做薄适配
    def _read(self, key: str) -> str | None:
        if self._use_redis_client:
            raw = self._r.get(key)  # type: ignore[union-attr]
            return raw.decode("utf-8") if isinstance(raw, bytes) else raw
        return self._r.get(key)  # type: ignore[union-attr]

    def _write(self, key: str, value: str) -> None:
        if self._use_redis_client:
            self._r.setex(key, self.ttl, value)  # type: ignore[union-attr]
        else:
            self._r.set(key, value, self.ttl)  # type: ignore[union-attr]

    def append(self, session_id: str, role: str, content: str) -> None:
        """追加一条消息并裁剪到窗口大小，同时刷新 TTL。"""
        history = self.get_history(session_id)
        history.append(Message(role=role, content=content, ts=time.time()))
        history = history[-self.window :]  # 滑动窗口
        payload = json.dumps([m.__dict__ for m in history], ensure_ascii=False)
        self._write(self._key(session_id), payload)

    def get_history(self, session_id: str) -> list[Message]:
        raw = self._read(self._key(session_id))
        if not raw:
            return []
        try:
            return [Message(**m) for m in json.loads(raw)]
        except (json.JSONDecodeError, TypeError):
            return []

    def recent_text(self, session_id: str, n: int = 6) -> str:
        """最近 n 条消息的纯文本拼接，供槽位继承使用。"""
        return "\n".join(f"{m.role}: {m.content}" for m in self.get_history(session_id)[-n:])

    def clear(self, session_id: str) -> None:
        self._write(self._key(session_id), json.dumps([]))
