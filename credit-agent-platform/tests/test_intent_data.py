"""意图训练数据格式校验（零外部依赖）。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JSONL = ROOT / "data" / "intent_samples.jsonl"
SFT = ROOT / "training" / "llama_factory" / "data" / "intent_sft.json"
DATASET_INFO = ROOT / "training" / "llama_factory" / "dataset_info.json"


@pytest.fixture(scope="module")
def samples():
    assert JSONL.exists(), f"训练样本不存在: {JSONL}（先运行 data/generate_intent_data.py）"
    return [json.loads(line) for line in JSONL.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_sample_count(samples):
    assert len(samples) >= 200, "仓库内至少应附带 200 条样例"


def test_sample_schema(samples):
    from src.intent.labels import is_valid_code

    for s in samples:
        assert set(s.keys()) == {"text", "intent"}, f"字段不符: {s.keys()}"
        assert isinstance(s["text"], str) and s["text"].strip(), "text 不能为空"
        assert is_valid_code(s["intent"]), f"非法意图标签: {s['intent']}"


def test_intent_coverage(samples):
    intents = {s["intent"] for s in samples}
    assert len(intents) >= 8, f"意图至少覆盖 8 类，当前 {len(intents)} 类"


def test_no_duplicate_text(samples):
    texts = [s["text"] for s in samples]
    assert len(texts) == len(set(texts)), "存在重复样本"


def test_generator_deterministic():
    from data.generate_intent_data import generate

    a = generate(n=120, seed=7)
    b = generate(n=120, seed=7)
    assert a == b, "相同种子应生成完全相同的数据"
    assert len(a) == 120


def test_generator_covers_all_intents():
    from data.generate_intent_data import generate

    from src.intent.labels import ALL_INTENTS

    intents = {s["intent"] for s in generate(n=200, seed=1)}
    assert intents == {i.code for i in ALL_INTENTS}


def test_sft_alpaca_format():
    assert SFT.exists(), "alpaca 格式 SFT 文件未生成"
    data = json.loads(SFT.read_text(encoding="utf-8"))
    assert isinstance(data, list) and len(data) >= 200
    for item in data[:50]:
        assert set(item.keys()) == {"instruction", "input", "output"}
        assert item["instruction"].strip() and item["input"].strip() and item["output"].strip()


def test_dataset_info_points_to_sft():
    info = json.loads(DATASET_INFO.read_text(encoding="utf-8"))
    assert "intent_sft" in info
    assert info["intent_sft"]["formatting"] == "alpaca"
    assert (DATASET_INFO.parent / info["intent_sft"]["file_name"]).exists()
