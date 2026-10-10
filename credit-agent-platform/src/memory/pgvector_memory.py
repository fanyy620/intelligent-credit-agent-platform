"""长期事实记忆：PGVector 语义抽取 + 向量检索。

分层记忆体系中的“慢”层：把跨会话值得留存的结构化事实
（月收入、借款用途、意向额度、职业、征信情况）抽取出来，
连同向量一起落库，下次会话按语义召回，实现“客户再来时我记得他”。

PostgreSQL/PGVector 不可用时降级为进程内向量库（hash 伪 embedding +
余弦相似度），接口完全一致，便于平滑切换。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from src.utils.embedding import hash_embed, cosine

# 建表 SQL（与 scripts/init_db.sql 保持一致，便于代码内引用与测试）
DDL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS user_facts (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    fact_key TEXT NOT NULL,            -- 事实类型：monthly_income / purpose / amount ...
    fact_value TEXT NOT NULL,          -- 事实内容（人类可读）
    embedding vector(256),             -- hash 伪 embedding；生产可换 bge-768 等
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, fact_key)
);

CREATE INDEX IF NOT EXISTS idx_user_facts_embedding
    ON user_facts USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);
""".strip()


@dataclass
class Fact:
    user_id: str
    fact_key: str
    fact_value: str
    ts: float = field(default_factory=time.time)
    similarity: float = 0.0  # 检索时填充

    def text(self) -> str:
        return f"{self.fact_key}: {self.fact_value}"


class _InMemoryVectorStore:
    """进程内向量库（PGVector 降级）。"""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim
        self._facts: dict[tuple[str, str], tuple[Fact, list[float]]] = {}

    def upsert(self, fact: Fact) -> None:
        key = (fact.user_id, fact.fact_key)
        self._facts[key] = (fact, hash_embed(fact.text(), dim=self.dim))

    def search(self, user_id: str, query: str, top_k: int) -> list[Fact]:
        q = hash_embed(query, dim=self.dim)
        scored: list[Fact] = []
        for (uid, _), (fact, vec) in self._facts.items():
            if uid != user_id:
                continue
            sim = cosine(q, vec)
            item = Fact(**{**fact.__dict__})
            item.similarity = round(sim, 4)
            scored.append(item)
        scored.sort(key=lambda f: f.similarity, reverse=True)
        return scored[:top_k]

    def all_facts(self, user_id: str) -> list[Fact]:
        return [f for (uid, _), (f, _) in self._facts.items() if uid == user_id]


class LongTermMemory:
    """长期事实记忆：PGVector 优先，内存向量库兜底。"""

    def __init__(self, database_url: str | None = None, dim: int = 256) -> None:
        self.dim = dim
        self.backend_name = "memory"
        self._mem = _InMemoryVectorStore(dim=dim)
        self._conn = None
        if database_url:
            try:
                import psycopg  # type: ignore

                self._conn = psycopg.connect(database_url, connect_timeout=2)
                with self._conn.cursor() as cur:
                    cur.execute("SELECT 1")
                self.backend_name = "pgvector"
            except Exception:
                self._conn = None

    # ------------------------------------------------------------- 写入

    def upsert_fact(self, user_id: str, fact_key: str, fact_value: str) -> None:
        """同一 (user_id, fact_key) 只保留最新值 —— 事实以新覆盖旧。"""
        fact = Fact(user_id=user_id, fact_key=fact_key, fact_value=fact_value)
        if self._conn is not None:
            vec = hash_embed(fact.text(), dim=self.dim)
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_facts (user_id, fact_key, fact_value, embedding, updated_at)
                    VALUES (%s, %s, %s, %s::vector, now())
                    ON CONFLICT (user_id, fact_key)
                    DO UPDATE SET fact_value = EXCLUDED.fact_value,
                                  embedding = EXCLUDED.embedding,
                                  updated_at = now()
                    """,
                    (user_id, fact_key, fact_value, "[" + ",".join(f"{v:.6f}" for v in vec) + "]"),
                )
            self._conn.commit()
        else:
            self._mem.upsert(fact)

    # ------------------------------------------------------------- 读取

    def search_facts(self, user_id: str, query: str, top_k: int = 5) -> list[Fact]:
        """按语义相似度召回该用户的相关事实。"""
        if self._conn is not None:
            q = "[" + ",".join(f"{v:.6f}" for v in hash_embed(query, dim=self.dim)) + "]"
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT fact_key, fact_value,
                           1 - (embedding <=> %s::vector) AS similarity
                    FROM user_facts
                    WHERE user_id = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (q, user_id, q, top_k),
                )
                return [
                    Fact(user_id=user_id, fact_key=r[0], fact_value=r[1],
                         similarity=round(float(r[2]), 4))
                    for r in cur.fetchall()
                ]
        return self._mem.search(user_id, query, top_k)

    def all_facts(self, user_id: str) -> list[Fact]:
        if self._conn is not None:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT fact_key, fact_value FROM user_facts WHERE user_id = %s ORDER BY fact_key",
                    (user_id,),
                )
                return [Fact(user_id=user_id, fact_key=r[0], fact_value=r[1]) for r in cur.fetchall()]
        return self._mem.all_facts(user_id)
