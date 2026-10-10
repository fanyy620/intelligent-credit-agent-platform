"""信贷产品目录：加载 configs/products.yaml 为结构化 Product 对象。

PyYAML 缺失时使用内置迷你解析器（仅支持本仓库 products.yaml 的平铺格式），
保证 demo / 测试零依赖可跑。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_YAML = PROJECT_ROOT / "configs" / "products.yaml"


@dataclass
class Product:
    id: str
    name: str
    category: str
    min_amount: float
    max_amount: float
    min_term_months: int
    max_term_months: int
    annual_rate_min: float
    annual_rate_max: float
    approval_hours: float
    min_age: int
    max_age: int
    min_monthly_income: float
    min_credit_score: int
    allowed_purposes: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    description: str = ""

    # ---- 展示辅助 ----
    @property
    def max_amount_wan(self) -> str:
        return f"{self.max_amount / 10000:g}万"

    @property
    def rate_min_pct(self) -> str:
        return f"{self.annual_rate_min * 100:g}%"

    @property
    def rate_range_pct(self) -> str:
        return f"{self.annual_rate_min * 100:g}%-{self.annual_rate_max * 100:g}%"

    def to_doc(self) -> str:
        """用于向量召回的文本化表示。"""
        return (
            f"{self.name} {self.category} {' '.join(self.tags)} "
            f"{' '.join(self.allowed_purposes)} {self.description}"
        )

    def summary(self) -> str:
        return (
            f"{self.name}（{self.category}）：额度{self.min_amount / 10000:g}-{self.max_amount_wan}，"
            f"期限{self.min_term_months}-{self.max_term_months}个月，"
            f"年化利率{self.rate_range_pct}，最快{self.approval_hours:g}小时审批"
        )


# ---------------------------------------------------------------- 迷你 YAML 解析

def _coerce(raw: str):
    raw = raw.strip()
    if raw == "":
        return ""
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def _mini_yaml_load(text: str) -> dict:
    """解析“一层平铺 list-of-dict”的 YAML 子集（products.yaml 专用）。"""
    items: list[dict] = []
    current: dict | None = None
    in_products = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped == "products:":
            in_products = True
            continue
        if not in_products:
            continue
        if stripped.startswith("- "):
            current = {}
            items.append(current)
            stripped = stripped[2:].strip()
            if not stripped:
                continue
        if current is not None and ":" in stripped:
            key, _, value = stripped.partition(":")
            current[key.strip()] = _coerce(value)
    return {"products": items}


def _load_yaml_dict(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text)
    except ImportError:
        return _mini_yaml_load(text)


def load_products(path: str | Path | None = None) -> list[Product]:
    """从 YAML 加载产品列表。"""
    yaml_path = Path(path) if path else DEFAULT_YAML
    data = _load_yaml_dict(yaml_path)
    products: list[Product] = []
    for item in data.get("products", []):
        item = dict(item)
        for key in ("allowed_purposes", "tags"):
            value = item.get(key, "")
            if isinstance(value, str):
                item[key] = [s for s in re.split(r"[,，]", value) if s]
        products.append(Product(**item))
    return products


_CACHE: dict[str, list[Product]] = {}


def get_catalog(path: str | Path | None = None, refresh: bool = False) -> list[Product]:
    """带缓存的产品目录单例。"""
    key = str(path or DEFAULT_YAML)
    if refresh or key not in _CACHE:
        _CACHE[key] = load_products(path)
    return _CACHE[key]
