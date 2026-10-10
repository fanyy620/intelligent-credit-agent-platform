"""意图训练数据生成脚本（模板化，确定性随机种子，可复现）。

运行：
    python data/generate_intent_data.py              # 生成 1000 条（默认）
    python data/generate_intent_data.py --n 200      # 指定条数

产物：
    data/intent_samples.jsonl                        # {"text","intent"} 逐行 JSON
    training/llama_factory/data/intent_sft.json      # LLaMA-Factory alpaca 格式

覆盖 10 类意图（见 src/intent/labels.py），话术模板按银行信贷真实
客服语料风格编写：口语化前缀/后缀随机拼接、金额期限用途随机填充。
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intent.labels import ALL_INTENTS  # noqa: E402

PRODUCTS = ["信享贷", "薪易贷", "极速信用贷", "学子助学贷",
            "兴业经营贷", "税易贷", "安居房抵贷", "车易贷"]
AMOUNTS = ["5万", "10万", "15万", "20万", "30万", "50万", "80万", "100万"]
TERMS = ["6个月", "1年", "2年", "3年", "5年", "36个月", "24个月"]
PURPOSES = ["装修", "孩子上学", "旅游", "进货", "店里周转", "买车", "看病", "扩大经营"]
OCCUPATIONS = ["上班族", "个体户", "开公司的", "自由职业", "公务员", "大学生"]

# ------------------------------------------------------------------ 模板库
# {p}=产品 {a}=金额 {t}=期限 {u}=用途 {o}=职业
TEMPLATES: dict[str, list[str]] = {
    "PRODUCT_CONSULT": [
        "你们都有什么贷款产品",
        "想了解一下消费贷款，介绍一下",
        "{p}是什么样的产品",
        "消费贷和经营贷有什么区别",
        "房抵贷和消费贷哪个更适合大额支出",
        "能介绍下{p}吗",
        "你们行有哪些信用贷产品",
        "车贷有哪些选择",
        "麻烦介绍一下你们的信贷产品",
        "小微企业贷款有哪些产品可以了解",
        "{p}和其他消费贷比有什么优势",
        "有没有不需要抵押的贷款产品",
        "我想了解一下贷款，你们有啥产品",
    ],
    "RATE_QUERY": [
        "{p}的利率是多少",
        "借{a}一年利息多少钱",
        "你们贷款利率最低多少",
        "{p}年化利率几厘",
        "现在消费贷利率多少",
        "{p}的费率怎么算",
        "借{a}分{t}还，利息一共多少",
        "房抵贷利率是不是比信用贷低",
        "{p}最近利率有优惠吗",
        "年化利率和月利率怎么换算",
        "税易贷的利率跟纳税等级有关吗",
        "利息是按月付还是到期一起付",
    ],
    "CREDIT_RECOMMEND": [
        "我月收入1万5，想借{a}{u}，帮我推荐一下",
        "我是{o}，需要{a}周转，能申请什么产品",
        "想借{a}，{t}内还清，征信良好，推荐个合适的",
        "{o}没有抵押物，能贷多少",
        "帮我看看我这种条件能申请哪个产品",
        "需要{a}用于{u}，期限{t}，哪个产品合适",
        "我征信一般，想借{a}，有戏吗",
        "给我推荐一个利率低点的贷款，借{a}{u}",
        "月薪八千想贷{a}，{u}用，能批吗",
        "我是个体户，店里要{u}，需要{a}，申请什么好",
        "孩子要出国留学，需要{a}，推荐下产品",
        "刚买了房想{u}，差{a}，帮我匹配个产品",
    ],
    "LIMIT_QUERY": [
        "{p}最多能贷多少",
        "我的条件最高能申请多少额度",
        "额度可以提升吗",
        "{p}的起借金额是多少",
        "月入一万大概能批多少额度",
        "为什么我的额度只有这么多",
        "最高额度是固定的吗",
        "想贷{a}，你们额度够吗",
        "额度批下来不用会收回去吗",
    ],
    "APPLY_PROCESS": [
        "怎么申请{p}",
        "申请贷款需要什么流程",
        "线上可以办理吗",
        "审批大概要多久",
        "申请之后多久能放款",
        "需要去网点面签吗",
        "{p}的申请入口在哪里",
        "周末可以提交申请吗",
        "审批被拒了可以再次申请吗",
        "办理贷款第一步要做什么",
    ],
    "REPAYMENT": [
        "等额本息和先息后本哪个划算",
        "可以提前还款吗，有违约金吗",
        "月供是怎么算出来的",
        "逾期一天会上征信吗",
        "还款日可以修改吗",
        "支持哪些还款方式",
        "提前还款能省多少利息",
        "{p}是按月还还是到期还本",
        "还不上可以协商延期吗",
    ],
    "COPYWRITING": [
        "帮我写一段{p}的朋友圈文案",
        "给{p}写个海报宣传语",
        "生成一条贷款产品的短信推广话术",
        "把这段文案改得更有吸引力",
        "写个面向{o}客群的营销文案",
        "帮我出三条{p}的推广标题",
        "写一段突出利率低的广告文案",
        "给车行客户写个车贷推广话术",
        "生成一篇{p}的公众号推文开头",
        "帮我润色一下这段营销文案",
    ],
    "MATERIALS": [
        "申请{p}需要什么材料",
        "要提供收入证明吗",
        "个体户申请要营业执照吗",
        "需要打银行流水吗",
        "房抵贷要准备哪些资料",
        "征信报告要自己提供吗",
        "申请经营贷需要纳税记录吗",
        "学生证可以申请助学贷吗",
        "材料不齐可以先提交吗",
    ],
    "CHITCHAT": [
        "你好",
        "在吗",
        "谢谢你啊",
        "今天天气真不错",
        "周末愉快",
        "再见",
        "你叫什么名字",
        "你是机器人吗",
        "辛苦了",
        "早上好",
        "哈哈好的",
        "没什么事了",
    ],
    "HUMAN_AGENT": [
        "转人工",
        "我要找人工客服",
        "帮我接客户经理",
        "机器人答非所问，转人工",
        "我要投诉",
        "有没有真人服务",
        "这个问题我要跟人工说",
        "联系一下我的客户经理",
        "别跟我绕了，叫人工来",
    ],
}

PREFIXES = ["", "", "", "你好，", "请问一下，", "打扰一下，", "您好，", "诶，", "麻烦问下，"]
SUFFIXES = ["", "", "", "？", "呢", "啊", "哈", "，谢谢", "，在线等"]


def generate(n: int = 1000, seed: int = 42) -> list[dict]:
    """生成 n 条 {"text","intent"} 样本，确定性可复现。"""
    rng = random.Random(seed)
    codes = [i.code for i in ALL_INTENTS]
    samples: list[dict] = []
    seen: set[str] = set()
    attempts = 0
    while len(samples) < n and attempts < n * 50:
        attempts += 1
        code = codes[len(samples) % len(codes)]  # 均衡分布
        template = rng.choice(TEMPLATES[code])
        text = template.format(
            p=rng.choice(PRODUCTS), a=rng.choice(AMOUNTS),
            t=rng.choice(TERMS), u=rng.choice(PURPOSES),
            o=rng.choice(OCCUPATIONS),
        )
        text = rng.choice(PREFIXES) + text + rng.choice(SUFFIXES)
        if text in seen:
            continue
        seen.add(text)
        samples.append({"text": text, "intent": code})
    rng.shuffle(samples)
    return samples


SFT_INSTRUCTION = (
    "你是银行信贷助手的意图分类器。请判断用户问题的意图，"
    "只输出意图标签编码（如 PRODUCT_CONSULT），不要输出其他内容。"
)


def to_alpaca(samples: list[dict]) -> list[dict]:
    """转为 LLaMA-Factory alpaca 格式。"""
    return [
        {"instruction": SFT_INSTRUCTION, "input": s["text"], "output": s["intent"]}
        for s in samples
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="生成意图识别训练数据")
    parser.add_argument("--n", type=int, default=1000, help="样本条数（默认 1000）")
    parser.add_argument("--seed", type=int, default=42, help="随机种子（默认 42）")
    parser.add_argument("--jsonl", type=Path, default=ROOT / "data" / "intent_samples.jsonl")
    parser.add_argument("--sft", type=Path,
                        default=ROOT / "training" / "llama_factory" / "data" / "intent_sft.json")
    args = parser.parse_args()

    samples = generate(n=args.n, seed=args.seed)

    args.jsonl.parent.mkdir(parents=True, exist_ok=True)
    with args.jsonl.open("w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    args.sft.parent.mkdir(parents=True, exist_ok=True)
    args.sft.write_text(
        json.dumps(to_alpaca(samples), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 分布统计
    dist: dict[str, int] = {}
    for s in samples:
        dist[s["intent"]] = dist.get(s["intent"], 0) + 1
    print(f"已生成 {len(samples)} 条样本（seed={args.seed}）")
    print(f"  JSONL : {args.jsonl}")
    print(f"  SFT   : {args.sft}")
    print("  意图分布:")
    for code, cnt in sorted(dist.items()):
        print(f"    {code:<18} {cnt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
