"""意图标签体系。

共 10 类，覆盖“产品咨询 → 利率/额度 → 授信推荐 → 流程/材料/还款 → 营销文案 → 闲聊/转人工”
的信贷营销与咨询全链路。训练数据生成、LoRA 微调、Prompt 路由共用此标签集。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IntentLabel:
    code: str          # 英文编码（LoRA 训练输出、日志埋点使用）
    zh: str            # 中文名
    description: str   # 判别要点（写入 Prompt 路由的提示词）
    examples: tuple[str, ...]


PRODUCT_CONSULT = IntentLabel(
    "PRODUCT_CONSULT", "产品咨询",
    "泛泛了解贷款产品种类、特点、差异，尚未给出自身条件",
    ("你们有什么贷款产品", "消费贷和经营贷有什么区别", "介绍一下房抵贷"),
)
RATE_QUERY = IntentLabel(
    "RATE_QUERY", "利率查询",
    "询问具体产品或某类贷款的利率、利息、月供成本",
    ("信享贷利率多少", "借20万一年利息多少钱", "年化利率最低多少"),
)
CREDIT_RECOMMEND = IntentLabel(
    "CREDIT_RECOMMEND", "授信推荐",
    "给出自身条件（收入/用途/金额/征信等），希望推荐或评估可贷产品",
    ("我月收入一万想借20万装修，推荐一下", "个体户能申请什么贷款", "帮我看看能批多少"),
)
LIMIT_QUERY = IntentLabel(
    "LIMIT_QUERY", "额度咨询",
    "单独追问额度上限、能贷多少、提额",
    ("最多能贷多少", "额度怎么提升", "我的额度够吗"),
)
APPLY_PROCESS = IntentLabel(
    "APPLY_PROCESS", "申请流程",
    "询问申请步骤、入口、审批时长、签约放款流程",
    ("怎么申请", "审批要多久", "线上可以办吗"),
)
REPAYMENT = IntentLabel(
    "REPAYMENT", "还款方式",
    "询问还款方式、月供、提前还款、逾期后果",
    ("等额本息和先息后本哪个好", "可以提前还款吗", "逾期一天会怎样"),
)
COPYWRITING = IntentLabel(
    "COPYWRITING", "文案生成",
    "要求生成或修改营销文案、朋友圈、海报语、短信话术",
    ("帮我写一段信享贷的朋友圈文案", "把这段文案改得更吸引人"),
)
MATERIALS = IntentLabel(
    "MATERIALS", "材料咨询",
    "询问申请所需材料、证明、资质文件",
    ("申请需要什么材料", "要收入证明吗", "营业执照要不要"),
)
CHITCHAT = IntentLabel(
    "CHITCHAT", "闲聊",
    "打招呼、感谢、与信贷无关的闲聊",
    ("你好", "谢谢", "今天天气怎么样"),
)
HUMAN_AGENT = IntentLabel(
    "HUMAN_AGENT", "转人工",
    "明确要求人工客服、投诉、对机器人不满",
    ("转人工", "我要投诉", "找客户经理"),
)

ALL_INTENTS: list[IntentLabel] = [
    PRODUCT_CONSULT, RATE_QUERY, CREDIT_RECOMMEND, LIMIT_QUERY,
    APPLY_PROCESS, REPAYMENT, COPYWRITING, MATERIALS,
    CHITCHAT, HUMAN_AGENT,
]

CODE_TO_LABEL: dict[str, IntentLabel] = {i.code: i for i in ALL_INTENTS}
ZH_TO_LABEL: dict[str, IntentLabel] = {i.zh: i for i in ALL_INTENTS}


def is_valid_code(code: str) -> bool:
    return code in CODE_TO_LABEL


def prompt_block() -> str:
    """供 Prompt 路由使用的标签说明段。"""
    lines = []
    for i, label in enumerate(ALL_INTENTS, 1):
        lines.append(f"{i}. {label.code}（{label.zh}）：{label.description}")
    return "\n".join(lines)
