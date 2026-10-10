"""槽位定义与抽取（三层推荐架构的第一道工序）。

双通道设计：
- extract_slots_rules：纯正则/词典，零依赖、可解释、毫秒级，覆盖
  金额、期限、用途、职业、收入、年龄、征信 7 个槽位；
- extract_slots_llm：把规则结果作为候选交给 LLM 复核补全（可选增强，
  无 LLM 时自动跳过）。两通道结果做“LLM 补缺、规则优先”合并。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict

# ------------------------------------------------------------------ 槽位 schema

@dataclass
class SlotSet:
    """一次推荐所需的业务槽位；None 表示用户未提供。"""

    amount: float | None = None          # 期望借款金额（元）
    term_months: int | None = None       # 期望期限（月）
    purpose: str | None = None           # 借款用途（装修/经营/购车...）
    occupation: str | None = None        # 职业身份（上班族/个体户/企业主/学生...）
    monthly_income: float | None = None  # 月收入（元）
    age: int | None = None
    credit_status: str | None = None     # 征信情况（良好/一般/有逾期）
    credit_score: int | None = None      # 估算征信分（由 credit_status 映射）

    def filled(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    def merge(self, other: "SlotSet") -> "SlotSet":
        """other 中已填写的槽位覆盖自身（用于跨轮槽位继承）。"""
        data = asdict(self)
        for k, v in asdict(other).items():
            if v is not None:
                data[k] = v
        return SlotSet(**data)


# ------------------------------------------------------------------ 词典

PURPOSE_WORDS = [
    "装修", "教育", "留学", "旅游", "医疗", "购车", "买车",
    "经营", "进货", "周转", "消费", "创业",
]
OCCUPATION_WORDS = {
    "上班族": "上班族", "白领": "上班族", "打工": "上班族", "工资": "上班族",
    "个体户": "个体户", "个体工商户": "个体户", "开店": "个体户",
    "企业主": "企业主", "开公司": "企业主", "小微企业": "企业主",
    "学生": "学生", "留学生": "学生",
    "自由职业": "自由职业",
}
_CREDIT_GOOD = ("征信良好", "征信很好", "信用良好", "没有逾期", "征信没问题")
_CREDIT_BAD = ("有逾期", "逾期过", "征信不好", "征信差", "黑户", "征信花")

# 征信描述 → 估算分（用于规则召回的硬过滤；真实场景应接征信接口）
_CREDIT_SCORE_MAP = {"良好": 650, "一般": 580, "有逾期": 520}


# ------------------------------------------------------------------ 正则工具

def _wan_to_yuan(num: float, unit_wan: bool) -> float:
    return num * 10000 if unit_wan else num


def _parse_amount(text: str) -> float | None:
    """解析金额：支持 “20万 / 20万元 / 1万5 / 200000 / 二十万(仅常见)”。"""
    m = re.search(r"(\d+(?:\.\d+)?)\s*万\s*(\d)?", text)
    if m:
        base = float(m.group(1)) * 10000
        if m.group(2):  # “1万5” → 15000
            base += int(m.group(2)) * 1000
        return base
    m = re.search(r"(\d{5,7})\s*(?:元|块)?", text)
    if m:
        return float(m.group(1))
    cn = re.search(r"([一二三四五六七八九十]+)万", text)
    if cn:
        table = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
                 "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
        return float(table.get(cn.group(1), 0)) * 10000 or None
    return None


def _parse_term(text: str) -> int | None:
    """解析期限：'3年' → 36，'24个月' → 24。"""
    m = re.search(r"(\d+)\s*个?月", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*年", text)
    if m:
        return int(m.group(1)) * 12
    return None


# ------------------------------------------------------------------ 规则抽取

def extract_slots_rules(text: str) -> SlotSet:
    """规则通道：对单句用户输入做槽位抽取。"""
    slots = SlotSet()
    masked = text  # 抽取收入后先遮蔽，避免“月收入1万5”被误识别为借款金额

    m = re.search(r"(?:月收入|月薪|工资|收入)\D{0,4}(\d+(?:\.\d+)?)\s*(万)?\s*(\d)?", text)
    if m:
        value = float(m.group(1))
        if m.group(2):
            value = value * 10000 + (int(m.group(3)) * 1000 if m.group(3) else 0)
        slots.monthly_income = value
        masked = masked[: m.start()] + " " * (m.end() - m.start()) + masked[m.end():]

    m = re.search(r"(\d{2})\s*岁", text)
    if m:
        slots.age = int(m.group(1))

    amount = _parse_amount(masked)
    if amount is not None:
        slots.amount = amount

    slots.term_months = _parse_term(text)

    for w in PURPOSE_WORDS:
        if w in text:
            slots.purpose = "购车" if w == "买车" else w
            break
    for w, label in OCCUPATION_WORDS.items():
        if w in text:
            slots.occupation = label
            break

    if any(k in text for k in _CREDIT_GOOD):
        slots.credit_status = "良好"
    elif any(k in text for k in _CREDIT_BAD):
        slots.credit_status = "有逾期"
    elif "征信一般" in text:
        slots.credit_status = "一般"
    if slots.credit_status:
        slots.credit_score = _CREDIT_SCORE_MAP.get(slots.credit_status)

    return slots


def extract_slots_llm(text: str, llm, base: SlotSet | None = None) -> SlotSet:
    """LLM 通道（可选增强）：无 LLM 或调用失败时原样返回规则结果。

    约定：LLM 只补全规则未命中的槽位，不覆盖规则已抽取的值
    （规则可解释、可审计，优先级高于模型）。
    """
    base = base or SlotSet()
    if llm is None or getattr(llm, "is_mock", False):
        return base
    try:
        extra = llm.extract_slots(text, schema=list(SlotSet.__dataclass_fields__))  # noqa: F821
    except Exception:
        return base
    merged = base
    for k, v in (extra or {}).items():
        if v is not None and getattr(merged, k, None) is None and hasattr(merged, k):
            merged = merged.merge(SlotSet(**{k: v}))
    return merged


def extract_slots(text: str, llm=None) -> SlotSet:
    """对外统一入口：规则优先，LLM 补缺。"""
    return extract_slots_llm(text, llm, base=extract_slots_rules(text))
