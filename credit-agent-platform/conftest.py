"""pytest 根配置：把项目根目录加入 sys.path，保证 tests 可 import src.*。

离线纪律：本机/CI 环境可能持久配置了真实 LLM Key（KIMI_API_KEY 等），
provider 自动探测链会据此接入真实模型，使单测产生网络依赖。
故默认强制 LLM_PROVIDER=mock，保证 `pytest tests/ -q` 永远零网络、确定性；
真实模型联调走 tests/test_live_llm.py，需显式 LIVE=1 才解除强制。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if os.environ.get("LIVE") != "1":
    os.environ["LLM_PROVIDER"] = "mock"
