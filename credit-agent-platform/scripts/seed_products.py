"""产品库灌库脚本：configs/products.yaml → PostgreSQL/PGVector。

前置：docker compose up -d（ postgres 健康检查通过后执行 ）
运行：python scripts/seed_products.py

向量说明：脚本写入哈希伪 embedding（256 维），与代码降级路径一致；
生产环境建议替换为 bge/text2vec 真实语义向量（改维度需同步
init_db.sql 与 src/memory/pgvector_memory.py 中的 vector(256)）。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from configs.settings import get_settings          # noqa: E402
from src.recommend.catalog import load_products    # noqa: E402
from src.utils.embedding import hash_embed         # noqa: E402


def main() -> int:
    settings = get_settings()
    products = load_products(settings.products_yaml)
    print(f"从 {settings.products_yaml} 加载 {len(products)} 个产品")

    try:
        import psycopg  # type: ignore
    except ImportError:
        print("缺少 psycopg，请先安装运行环境依赖：pip install \"psycopg[binary]\"")
        return 1

    try:
        conn = psycopg.connect(settings.database_url, connect_timeout=3)
    except Exception as e:
        print(f"无法连接数据库（{e}）。请先启动：docker compose up -d")
        return 1

    with conn.cursor() as cur:
        for p in products:
            vec = "[" + ",".join(f"{v:.6f}" for v in hash_embed(p.to_doc())) + "]"
            cur.execute(
                """
                INSERT INTO products (id, name, category, min_amount, max_amount,
                    min_term_months, max_term_months, annual_rate_min, annual_rate_max,
                    approval_hours, min_age, max_age, min_monthly_income,
                    min_credit_score, allowed_purposes, tags, description, embedding)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)
                ON CONFLICT (id) DO UPDATE SET
                    name=EXCLUDED.name, category=EXCLUDED.category,
                    min_amount=EXCLUDED.min_amount, max_amount=EXCLUDED.max_amount,
                    min_term_months=EXCLUDED.min_term_months,
                    max_term_months=EXCLUDED.max_term_months,
                    annual_rate_min=EXCLUDED.annual_rate_min,
                    annual_rate_max=EXCLUDED.annual_rate_max,
                    approval_hours=EXCLUDED.approval_hours,
                    min_age=EXCLUDED.min_age, max_age=EXCLUDED.max_age,
                    min_monthly_income=EXCLUDED.min_monthly_income,
                    min_credit_score=EXCLUDED.min_credit_score,
                    allowed_purposes=EXCLUDED.allowed_purposes,
                    tags=EXCLUDED.tags, description=EXCLUDED.description,
                    embedding=EXCLUDED.embedding, updated_at=now()
                """,
                (p.id, p.name, p.category, p.min_amount, p.max_amount,
                 p.min_term_months, p.max_term_months, p.annual_rate_min,
                 p.annual_rate_max, p.approval_hours, p.min_age, p.max_age,
                 p.min_monthly_income, p.min_credit_score,
                 p.allowed_purposes, p.tags, p.description, vec),
            )
    conn.commit()
    conn.close()
    print(f"灌库完成：{len(products)} 个产品已写入 products 表（含向量）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
