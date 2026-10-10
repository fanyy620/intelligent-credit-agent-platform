-- 初始化脚本：docker-compose 首次启动 postgres 时自动执行
-- （挂载到 /docker-entrypoint-initdb.d/00_init.sql）

CREATE EXTENSION IF NOT EXISTS vector;

-- 信贷产品表：业务字段 + 向量列（哈希伪 embedding 256 维；
-- 生产环境换 bge 等模型时把维度改为 768/1024 并重建索引）
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    min_amount NUMERIC NOT NULL,
    max_amount NUMERIC NOT NULL,
    min_term_months INT NOT NULL,
    max_term_months INT NOT NULL,
    annual_rate_min NUMERIC NOT NULL,
    annual_rate_max NUMERIC NOT NULL,
    approval_hours NUMERIC NOT NULL,
    min_age INT NOT NULL,
    max_age INT NOT NULL,
    min_monthly_income NUMERIC NOT NULL DEFAULT 0,
    min_credit_score INT NOT NULL DEFAULT 0,
    allowed_purposes TEXT[] NOT NULL DEFAULT '{}',
    tags TEXT[] NOT NULL DEFAULT '{}',
    description TEXT NOT NULL DEFAULT '',
    embedding vector(256),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_products_embedding
    ON products USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

-- 长期事实记忆表：同一用户同一事实键只保留最新值
CREATE TABLE IF NOT EXISTS user_facts (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    fact_key TEXT NOT NULL,
    fact_value TEXT NOT NULL,
    embedding vector(256),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, fact_key)
);

CREATE INDEX IF NOT EXISTS idx_user_facts_user ON user_facts (user_id);
CREATE INDEX IF NOT EXISTS idx_user_facts_embedding
    ON user_facts USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);
