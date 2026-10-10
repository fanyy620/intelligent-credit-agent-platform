# -*- coding: utf-8 -*-
"""双视角辩论层（中金 Multi-Agent 方法论映射）。

对外只暴露 run_debate / detect_hard_issues 与数据结构；
用法见 src/agent/nodes.py node_recommend 中的集成点。
"""
from src.debate.engine import (
    DebateResult, Perspective, detect_hard_issues, run_debate,
)

__all__ = ["DebateResult", "Perspective", "detect_hard_issues", "run_debate"]
