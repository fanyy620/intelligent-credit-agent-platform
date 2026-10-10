"""纯 Python 文本向量化工具。

无 PGVector / 无 embedding 模型时的降级方案：
- 中文字符一元+二元 gram，经 MD5 哈希映射到固定维度向量；
- L2 归一化后用余弦相似度比较。
该方案不具备真正的语义理解能力，但对“关键词重合度”敏感，
足以支撑 demo、单测与召回链路的联调。接入真实环境后可整体替换
为 bge / text2vec 等 embedding 模型，接口保持不变。
"""
from __future__ import annotations

import hashlib
import math
import re

_PUNCT = re.compile(r"[\s，。！？、；：,.!?;:（）()【】\[\]\"'“”‘’]+")


def _ngrams(text: str) -> list[str]:
    """抽取一元/二元字符 gram（去标点后）。"""
    cleaned = _PUNCT.sub("", text.lower())
    grams = list(cleaned)  # 一元
    grams += [cleaned[i : i + 2] for i in range(len(cleaned) - 1)]  # 二元
    return grams


def hash_embed(text: str, dim: int = 256) -> list[float]:
    """哈希伪 embedding：gram 计数投影到 dim 维并做 L2 归一化。"""
    vec = [0.0] * dim
    for gram in _ngrams(text):
        digest = hashlib.md5(gram.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "little") % dim
        # 用另一段字节决定 +/-，模拟随机投影，降低哈希碰撞的同向偏置
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度（输入已归一化时即点积；这里仍做防御性归一化）。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
