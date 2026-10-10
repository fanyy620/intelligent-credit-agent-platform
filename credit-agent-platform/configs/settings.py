"""全局配置。

设计说明：
- 使用标准库 dataclass 实现，零第三方依赖，保证 demo / tests 开箱即跑；
- 生产环境可无缝替换为 pydantic-settings（字段一一对应，见 README）；
- 所有配置均可被环境变量覆盖，本地开发可复制 .env.example 为 .env。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path) -> dict[str, str]:
    """极简 .env 解析（KEY=VALUE，支持 # 注释），避免依赖 python-dotenv。"""
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


@dataclass
class Settings:
    """应用配置；字段默认值与 .env.example 保持一致。"""

    # ---- 大模型 ----
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # ---- Kimi（Moonshot，OpenAI 兼容；provider 探测链见 src/llm/client.py get_llm）----
    llm_provider: str = "auto"        # auto / mock / kimi / deepseek（mock 强制离线替身）
    kimi_api_key: str = ""
    kimi_base_url: str = "https://api.kimi.com/coding/v1"
    kimi_model: str = "kimi-for-coding-highspeed"
    moonshot_api_key: str = ""        # KIMI_API_KEY 的别名，二者任一即可
    llm_timeout: float = 45.0         # 单次 LLM 调用超时（秒）
    llm_temperature: float = 1.0      # Kimi for Coding 端点仅允许 1；公共端点可调低
    llm_max_tokens: int = 2048        # reasoning 模型会把预算消耗在思考上，需给足

    # ---- 存储 ----
    database_url: str = "postgresql://postgres:postgres@localhost:5432/credit_agent"
    redis_url: str = "redis://localhost:6379/0"

    # ---- Langfuse 可观测 ----
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "http://localhost:3000"

    # ---- LoRA 意图模型 ----
    intent_model_path: str = "models/intent-lora-merged"

    # ---- 产品库 ----
    products_yaml: str = str(PROJECT_ROOT / "configs" / "products.yaml")

    # ---- 第三层重排权重（业务评分，四者之和应为 1.0）----
    weight_amount: float = 0.30   # 额度匹配度
    weight_term: float = 0.20     # 期限灵活度
    weight_rate: float = 0.30     # 利率优惠度
    weight_speed: float = 0.20    # 审批速度
    semantic_weight: float = 0.25  # 最终分 = (1-w)*业务分 + w*语义分

    # ---- 记忆 ----
    session_ttl_seconds: int = 3600   # Redis 短期记忆 TTL
    session_window: int = 20          # 滑动窗口：最多保留的会话消息条数
    memory_fact_top_k: int = 5        # 长期事实记忆召回条数

    # ---- 伪向量 ----
    embedding_dim: int = 256          # 哈希伪 embedding 维度（无 PG/真实模型时使用）

    @classmethod
    def from_env(cls, use_dotenv: bool = True) -> "Settings":
        """从 .env + 环境变量构建配置，环境变量优先级更高。"""
        merged: dict[str, str] = {}
        if use_dotenv:
            merged.update(_load_dotenv(PROJECT_ROOT / ".env"))
        merged.update(os.environ)

        kwargs: dict[str, object] = {}
        for f in fields(cls):
            env_key = f.name.upper()
            if env_key not in merged or merged[env_key] == "":
                continue
            raw = merged[env_key]
            if f.type in ("int", int):
                kwargs[f.name] = int(raw)
            elif f.type in ("float", float):
                kwargs[f.name] = float(raw)
            else:
                kwargs[f.name] = raw
        return cls(**kwargs)


_CACHE: Settings | None = None


def get_settings(refresh: bool = False) -> Settings:
    """进程级配置单例。"""
    global _CACHE
    if _CACHE is None or refresh:
        _CACHE = Settings.from_env()
    return _CACHE
