"""双重风控之【第一重】：正则硬性拦截。

内置银行营销违规话术词库（依据《商业银行互联网贷款管理暂行办法》及
广告法对金融营销宣传的常见要求整理的教学版），命中即拦截并给出修改建议。
该层特点是零延迟、可解释、可审计，是合规链路的底线。
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ViolationRule:
    name: str            # 规则名（埋点/日志使用）
    pattern: re.Pattern  # 命中正则
    reason: str          # 违规原因
    suggestion: str      # 修改建议


@dataclass
class Violation:
    rule_name: str
    matched: str
    reason: str
    suggestion: str


def _p(pattern: str) -> re.Pattern:
    return re.compile(pattern)


# 教学版违规词库：可按行内合规部门最新要求扩充
RULES: list[ViolationRule] = [
    ViolationRule(
        "承诺保本保息",
        _p(r"保本|保息|刚性兑付|刚兑|本息保障"),
        "存款/理财/贷款营销不得承诺保本保息",
        "改为“利率以审批结果为准”等风险提示表述",
    ),
    ViolationRule(
        "承诺百分百下款",
        _p(r"百分百|100%|百分之百|必下款|包下款|包过|必过|保证下款|稳下款"),
        "贷款审批存在不确定性，不得承诺必然放款",
        "改为“最快X小时审批”“通过率较高”并附“以实际审批为准”",
    ),
    ViolationRule(
        "无视征信",
        _p(r"无视征信|不看征信|不上征信|征信不好也能|黑户可做|无视黑白户|黑白户都行|洗白征信"),
        "不得宣称规避征信审核，属于严重违规宣传",
        "删除该表述；如针对轻瑕疵客群可写“综合评估，不以单一征信维度拒贷”",
    ),
    ViolationRule(
        "承诺收益",
        _p(r"稳赚不赔|躺着赚|年化收益保证|收益承诺|无风险高收益"),
        "不得承诺投资收益或淡化风险",
        "删除收益承诺，增加风险提示语",
    ),
    ViolationRule(
        "内部渠道包装",
        _p(r"内部渠道|内部指标|内部名额|走后门|特殊关系|银行内部有人"),
        "不得虚构内部渠道诱导客户",
        "删除虚构表述，说明正规申请入口",
    ),
    ViolationRule(
        "隐瞒费用/零费用噱头",
        _p(r"零利息|免息贷款|无任何费用|不收取任何费用"),
        "贷款定价须明示年化利率，不得以“零费用”误导",
        "明示年化利率区间及可能费用",
    ),
    ViolationRule(
        "诱导以贷养贷",
        _p(r"以贷养贷|借新还旧没问题|多头借贷|套现"),
        "不得诱导客户过度负债",
        "删除诱导性表述，提示理性借贷",
    ),
    ViolationRule(
        "夸大额度/时限",
        _p(r"人人可贷|无门槛|秒批秒到(?!账以)|想贷多少贷多少"),
        "不得夸大宣传审批确定性与额度",
        "改为区间化表述并附审批前提",
    ),
]


def check(text: str) -> list[Violation]:
    """扫描文本，返回全部违规项（可能多条）。"""
    hits: list[Violation] = []
    for rule in RULES:
        for m in rule.pattern.finditer(text):
            hits.append(
                Violation(
                    rule_name=rule.name,
                    matched=m.group(0),
                    reason=rule.reason,
                    suggestion=rule.suggestion,
                )
            )
    return hits


def is_compliant(text: str) -> bool:
    return not check(text)


def redact(text: str) -> str:
    """教学演示用：把违规片段替换为占位符（生产环境应整体拦截重写）。

    注意占位符不携带规则名与命中词，避免违规话术在输出中二次曝光。
    """
    out = text
    for rule in RULES:
        out = rule.pattern.sub("〔违规话术已拦截〕", out)
    return out
