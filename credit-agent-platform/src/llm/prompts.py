"""Prompt 工程层：五层 LLM 提示词的单一事实来源。

设计总原则（每层 prompt 内注释展开）：

1. **人设统一**：南洋商业银行（中国）对公信贷顾问，专业稳健、不夸大、
   不承诺审批结果 —— 与品牌定位（对公信贷）和合规要求一致。
2. **结构化输出**：除推荐解释外均要求 JSON/定界标签输出，配合
   client.py 的鲁棒解析（剥 fence → 找首尾 {} → 修复重试一次 → 确定性降级）。
3. **few-shot 锚定难点**：示例刻意覆盖易混淆边界（额度咨询 vs 授信推荐、
   对公场景槽位、合规换皮话术），而非堆砌数量。
4. **数值纪律**：LLM 永远不产出业务数值的“事实”——利率/额度等数字
   一律来自结构化目录（template_fill 渲染），提示词层同步明令禁止，
   形成“提示词约束 + 代码拦截”双保险。

五层对应：意图 INTENT / 槽位 SLOT / 回复 REPLY / 文案模板 COPY / 语义审核 COMPLIANCE；
另设合规重写 REWRITE 层（对话回复被拦后的重写兜底，见 §6）。
"""
from __future__ import annotations

import json

from src.intent.labels import prompt_block

# 南洋商业银行对公信贷顾问人设（五层共用，保证口吻一致）
PERSONA = (
    "你是南洋商业银行（中国）的智能信贷顾问，服务小微企业主、个体工商户与个人客户，"
    "提供贷款产品咨询、授信方案推荐与合规营销文案服务。"
    "风格要求：专业、稳健、精炼；不夸大收益，不承诺审批结果，不编造任何数字。"
)

# 解析失败时的修复指令（client.py 重试时追加为新一轮 user 消息）
REPAIR_HINT = (
    "你的上次输出无法被程序解析。请严格按要求重新输出："
    "只输出要求的内容本身（JSON 对象或指定标签），"
    "不要输出解释、寒暄、markdown 代码块标记或任何其他文字。"
)

# PIT（Point-in-Time）数据时点约束 —— 中金《Multi-Agent 如何辩论出基本面 Alpha》
# 方法论在信贷语境的等价物：研报用 PIT 限定数据可得时点防未来信息泄露，
# 本系统在 prompt 层限定"信息可得范围"防越权推断（详见 docs/cicc-methodology-mapping.md）。
PIT_CLAUSE = (
    "数据纪律（PIT 时点约束）：仅使用用户在对话中已提供的信息与产品库静态数据；"
    "不得假设或推断用户未提供的财务数据（收入、负债、征信记录等），"
    "不得使用对话之外的任何外部信息。"
)


def _msgs(system: str, pairs: list[tuple[str, str]], user: str) -> list[dict]:
    """组装 messages：system + few-shot 问答对 + 真实用户输入。

    few-shot 走真实的 user/assistant 轮次（而非塞进 system 文本），
    对 chat 模型的格式锚定效果更好。
    """
    messages = [{"role": "system", "content": system}]
    for u, a in pairs:
        messages.append({"role": "user", "content": u})
        messages.append({"role": "assistant", "content": a})
    messages.append({"role": "user", "content": user})
    return messages


# ------------------------------------------------------------------ 1. 意图 INTENT

def intent_messages(text: str) -> list[dict]:
    """意图分类：从 10 类标签中选一个，输出 JSON {"intent": code, "reason": ...}。

    设计说明：
    - 选 JSON 而非裸标签，是为了让模型顺带给出可审计的判别理由（进 trace 日志）；
      解析端同时兼容裸标签输出，保证弱模型/异常输出仍可解析；
    - few-shot 锚定三个易混点：① 只问“能贷多少”是额度咨询而非授信推荐
      （未给用途/条件）；② 对公复合句（制造业+200万+流动资金）是授信推荐；
      ③ 要求“写文案”即使带产品名也是文案生成而非产品咨询。
    """
    system = (
        PERSONA + "\n\n"
        "你的任务：判断用户一句话的意图，从下列 10 个标签中选【唯一】最贴切的。\n"
        + prompt_block() + "\n\n"
        "输出契约：只输出一行 JSON：{\"intent\": \"标签编码\", \"reason\": \"不超过20字的判别理由\"}。"
        "intent 取值必须原样来自上表编码；拿不准时输出 CHITCHAT。"
    )
    pairs = [
        ("你们行的经营贷和消费贷有什么区别",
         '{"intent": "PRODUCT_CONSULT", "reason": "泛泛比较产品差异"}'),
        ("税易贷的年化利率最低多少",
         '{"intent": "RATE_QUERY", "reason": "询问具体产品利率"}'),
        ("我最多能贷多少",
         '{"intent": "LIMIT_QUERY", "reason": "单问额度上限，未给条件"}'),
        ("我们是制造业企业，需要200万流动资金贷款，期限12个月，请帮我推荐合适的信贷产品",
         '{"intent": "CREDIT_RECOMMEND", "reason": "给出自身条件求推荐"}'),
        ("帮我写一段税易贷的朋友圈文案",
         '{"intent": "COPYWRITING", "reason": "要求生成营销文案"}'),
        ("在吗",
         '{"intent": "CHITCHAT", "reason": "打招呼，无业务诉求"}'),
    ]
    return _msgs(system, pairs, text)


# ------------------------------------------------------------------ 2. 槽位 SLOT

# 槽位取值词表（与 src/recommend/slots.py 规则通道对齐，保证两通道语义一致）
_SLOT_VOCAB = (
    "取值约定：amount/monthly_income 为数值（单位：元，例如 20万 → 200000）；"
    "term_months/age/credit_score 为整数（期限单位：月，例如 3年 → 36）；"
    "purpose 限于：经营/周转/进货/消费/装修/教育/留学/旅游/医疗/购车；"
    "occupation 限于：上班族/个体户/企业主/自由职业/学生；"
    "credit_status 限于：良好/一般/有逾期。"
)


def slot_messages(text: str, schema: list[str]) -> list[dict]:
    """槽位抽取：输出 JSON 对象，键限于 schema，缺失的信息不输出。

    设计说明：
    - “流动资金贷款/进货款”这类对公表述映射为 purpose=经营或周转、
      occupation=企业主——规则通道覆盖不了的口语变体由 few-shot 显式教会；
    - 明令“没有的信息不要输出、不得推测”，把幻觉挡在槽位层；
      client 端再做类型校验与 schema 白名单过滤（第二道闸）。
    """
    system = (
        PERSONA + "\n\n"
        "你的任务：从用户话语中抽取信贷业务槽位，只输出一个 JSON 对象。\n"
        f"允许的键（没有提及的键一律不输出）：{', '.join(schema)}。\n"
        + _SLOT_VOCAB + "\n"
        "纪律：只抽取用户明确说出的信息，禁止推测、禁止编造、禁止输出 schema 之外的键。\n"
        + PIT_CLAUSE
    )
    pairs = [
        ("我月收入1万5，想借20万装修房子，3年内还清，征信良好",
         json.dumps({"monthly_income": 15000, "amount": 200000, "purpose": "装修",
                     "term_months": 36, "credit_status": "良好"}, ensure_ascii=False)),
        ("我们是制造业企业，需要200万流动资金贷款，期限12个月",
         json.dumps({"amount": 2000000, "term_months": 12, "purpose": "经营",
                     "occupation": "企业主"}, ensure_ascii=False)),
        ("你们有什么贷款产品", "{}"),
    ]
    return _msgs(system, pairs, text)


# ------------------------------------------------------------------ 3. 回复 REPLY

def reply_messages(product_name: str, slots: dict) -> list[dict]:
    """推荐理由：一句话说明“为什么这个产品适合这位客户”。

    设计说明：
    - 这是五层中唯一允许自由文本的层，但只允许“解释”，不允许“给数”：
      数字只能复述 slots 中已有的客户条件，产品侧数值（额度/利率/时效）
      由节点代码从结构化目录拼出 —— 从提示词上切断报价幻觉路径；
    - 限制一句话 40 字以内：推荐卡片上可读，且越短越难编造。
    """
    system = (
        PERSONA + "\n\n"
        "你的任务：用【一句话】（40 字以内）说明为什么向该客户推荐此产品。\n"
        "纪律：只能引用下面给出的客户条件与产品名称；不得出现任何产品数值"
        "（额度、利率、期限、时效由系统另行展示）；不得承诺审批结果。\n"
        + PIT_CLAUSE
    )
    pairs = [
        ('产品：兴业经营贷；客户条件：{"amount": 500000, "purpose": "进货", "occupation": "个体户"}',
         "个体户进货用款50万，该产品正是面向经营场景的纯信用贷款。"),
    ]
    user = f"产品：{product_name}；客户条件：{json.dumps(slots, ensure_ascii=False)}"
    return _msgs(system, pairs, user)


# ------------------------------------------------------------------ 4. 文案模板 COPY

COPY_SLOT_WHITELIST = (
    "{product_name} {category} {max_amount} {min_amount} {rate_min} "
    "{rate_max} {min_term} {max_term} {approval_hours}"
)


def copy_messages(product_name: str, tone: str = "亲切专业") -> list[dict]:
    """营销文案【模板】：只允许槽位占位符，严禁任何数字。

    设计说明（防数值幻觉的核心层）：
    - 模型若直接写数字（如“最高50万”），可能与真实产品参数不符，构成
      误导宣传。故提示词层明令“禁止出现任何阿拉伯数字”，数值一律用
      白名单槽位表示，由 template_fill 用结构化数据渲染成稿；
    - 代码侧 find_free_numbers() 会二次扫描，越权数字整篇拒渲染——
      提示词约束 + 代码拦截双保险；
    - few-shot 给出“正确模板长什么样”，比单纯文字禁令更能稳定输出格式。
    """
    system = (
        PERSONA + "\n\n"
        "你的任务：为指定贷款产品写一段朋友圈推广文案【模板】，80 字以内。\n"
        "硬性要求：\n"
        "1) 严禁出现任何阿拉伯数字与数值表述，所有数值一律用槽位表示，"
        f"可选槽位仅限：{COPY_SLOT_WHITELIST}；\n"
        "2) 不得承诺保本保息、百分百下款、无视征信、内部渠道；"
        "不得使用“首选/最佳/第一/顶级/唯一”等绝对化用语（违反广告法）；\n"
        "3) 模板中保留 {product_name} 槽位，不要直接写死产品名。"
    )
    pairs = [
        ("产品：信享贷，语气：亲切专业",
         "【{product_name}】{category}新选择：额度最高{max_amount}，"
         "年化利率低至{rate_min}起，{min_term}-{max_term}个月灵活期限，"
         "最快{approval_hours}小时出审批结果。线上申请，流程透明。"),
    ]
    return _msgs(system, pairs, f"产品：{product_name}，语气：{tone}")


# ------------------------------------------------------------------ 5. 语义审核 COMPLIANCE

def compliance_messages(text: str) -> list[dict]:
    """合规复核：输出 JSON {"verdict": "PASS"|"BLOCK", "reason": ...}。

    设计说明：
    - 定位为正则硬拦截之后的“语义第二意见”：专抓换皮表达
      （如“保证都能批下来”不含任何正则关键词但语义违规），故判定口径
      宁严勿宽——拿不准一律 BLOCK，误伤由人工复核兜底；
    - few-shot 一正一反：合规报价（数值来自系统渲染）应 PASS；
      无任何脏字但承诺“都能批”的换皮话术应 BLOCK；
    - 解析端兼容裸 PASS/BLOCK 输出，弱模型也不致卡死链路。
    """
    system = (
        PERSONA + "\n\n"
        "你的任务：审核以下银行营销文案是否符合监管与行内宣传规范。\n"
        "违规情形包括但不限于：承诺保本保息、承诺百分百下款或通过审批、"
        "宣称无视征信/黑白户均可、暗示内部关系可操作、隐瞒费用、"
        "使用“首选/最佳/第一/顶级”等绝对化用语做产品宣传、夸大额度或压低利率误导客户。\n"
        "边界（易误判点）：产品推荐列表中的排序标签（Top1/Top2 等中性序号）、"
        "顾问对话中基于产品事实的客观介绍与推荐理由，不属于绝对化用语，不得据此判违规。\n"
        "判定口径：拿不准时一律视为违规（宁严勿宽）。\n"
        '输出契约：只输出一行 JSON：{"verdict": "PASS" 或 "BLOCK", "reason": "不超过20字理由"}。'
    )
    pairs = [
        ("信享贷最高可借30万，年化利率低至4.8%起，具体以审批结果为准",
         '{"verdict": "PASS", "reason": "如实报价且附审批提示"}'),
        ("这款产品保证都能批下来，不管征信多差都能做",
         '{"verdict": "BLOCK", "reason": "承诺必过且无视征信"}'),
        ("根据您的情况，为您推荐以下产品（按综合评分排序）：\n"
         "  Top1 税易贷（经营贷）综合分 0.614\n"
         "      额度10-300万，年化3.85%-6.5%，6-36个月，最快48小时审批\n"
         "      推荐理由：您为企业主且用于经营，税易贷基于纳税记录提供融资支持。\n"
         "以上额度和利率均以最终审批为准。",
         '{"verdict": "PASS", "reason": "排序标签为中性序号，客观介绍"}'),
    ]
    return _msgs(system, pairs, text)


# ------------------------------------------------------------------ 6. 合规重写 REWRITE（对话回复专用）

def rewrite_messages(text: str, issues: list[str] | None = None) -> list[dict]:
    """对话回复的合规重写：保留业务信息与数值，去除违规表述。

    设计说明：
    - 对话轮被合规拦截后，兜底绝不能是营销模板（答非所问）——本层让
      LLM 按合规约束把原回复重出一版，保住对话语境与推荐信息；
    - 数值纪律不变：原回复中的数值全部来自结构化目录（唯一事实来源），
      重写必须原样保留、不得增删任何数字，防止重写层引入新幻觉；
    - 输出即最终回复全文，禁止输出解释或“合规/重写”等元信息。
    """
    system = (
        PERSONA + "\n\n"
        "你的任务：把一段未通过合规审核的信贷顾问回复，改写为合规版本后重新输出。\n"
        "要求：\n"
        "1) 保留原回复的业务信息（推荐产品、推荐理由、需要客户补充的信息），"
        "维持顾问式对话口吻；\n"
        "2) 原回复中的数值（额度/利率/期限/时效/评分）必须原样保留，"
        "不得修改、不得新增任何数字；\n"
        "3) 删除或改写违规表述（承诺审批结果、绝对化用语、误导性宣传等）；\n"
        "4) 只输出改写后的回复全文，不要解释、不要提及“合规”“重写”等元信息。"
    )
    user = text if not issues else f"违规点：{'；'.join(issues)}\n\n原回复：\n{text}"
    return _msgs(system, [], user)


# ------------------------------------------------------------------ 7. 网站动作 SITE_ACTION（Copilot 模式）

def site_action_messages(text: str, page: str | None = None) -> list[dict]:
    """模糊语义 → 结构化网站动作列表（function calling 思路）。

    设计说明：
    - 与 INTENT 层分工：INTENT 判"对话意图"驱动回复管线，本层判"操作意图"
      驱动前端页面动作，两者并存（响应中 actions 与 reply 并存，前端
      先执行动作再展示回复）；
    - 动作白名单与前端执行器一一对应，非白名单动作由 client 端丢弃
      （提示词约束 + 代码白名单双保险，防"幻觉动作"）；
    - 参数抽取纪律：企业名/产品名【保留用户原话中的关键称谓】（如"华创"），
      不做臆造补全——模糊匹配到完整名称（"华创精密制造有限公司"）是前端
      执行器的职责（它有真实数据，Agent 没有客户库访问权）；
    - few-shot 刻意覆盖模糊语义：口语称谓（"华创那家公司"）、泛化问法
      （"最近业务怎么样"）、场景化表达（"发个朋友圈宣传下"）。
    """
    system = (
        PERSONA + "\n\n"
        "你的任务：理解用户一句话的【网站操作意图】，输出要执行的动作列表（JSON）。\n"
        "动作白名单（type 与参数）：\n"
        '- navigate {"path": "..."}：打开页面，路径限 /dashboard /customer /product '
        "/recommend /copy /chat /profile\n"
        '- search_customer {"keyword": "..."}：跳企业客户页并按关键词筛选（模糊匹配企业名/行业）\n'
        '- view_customer {"name": "..."}：查看某企业客户详情，name 用原话关键称谓\n'
        '- open_product {"name": "..."}：查看某信贷产品\n'
        '- generate_copy {"product_name": "...(可选)", "channel": "...(可选)"}：发起营销文案生成\n'
        "- show_stats {}：查看今日看板数据\n"
        "- recommend {}：授信推荐（用户给出用途/金额/期限等条件求推荐时用）\n"
        "- none {}：纯对话，无需任何页面动作\n"
        "输出契约：只输出一行 JSON：{\"actions\": [{\"type\": \"...\", \"params\": {...}}]}；"
        "纯对话输出 {\"actions\": [{\"type\": \"none\", \"params\": {}}]}；"
        "最多 2 个动作，按执行顺序排列；type 不得超出白名单。"
    )
    pairs = [
        ("帮我看看华创那家公司情况",
         '{"actions": [{"type": "view_customer", "params": {"name": "华创"}}]}'),
        ("最近业务怎么样",
         '{"actions": [{"type": "show_stats", "params": {}}]}'),
        ("我想发个朋友圈宣传下税易贷",
         '{"actions": [{"type": "generate_copy", "params": {"product_name": "税易贷", "channel": "朋友圈"}}]}'),
        ("制造业要200万周转一年推荐下",
         '{"actions": [{"type": "recommend", "params": {}}]}'),
        ("去产品页看看",
         '{"actions": [{"type": "navigate", "params": {"path": "/product"}}]}'),
        ("你好",
         '{"actions": [{"type": "none", "params": {}}]}'),
    ]
    user = f"当前页面：{page}\n用户说：{text}" if page else f"用户说：{text}"
    return _msgs(system, pairs, user)


# ------------------------------------------------------------------ 8. 双视角辩论 DEBATE（中金 Multi-Agent 方法论映射）

# 两个视角对应中金研报「质量/价值 Agent × 成长/动量 Agent」的双视角设计：
# 围绕同一推荐结果相互校验（"提质"），并以视角分工避免单一叙事（"去同质"）。
DEBATE_PERSPECTIVES = {
    "risk": (
        "风险合规视角：你只关注风险——偿债能力、征信状况、现金流真实性、"
        "抵押与担保保护、用途与产品准入的匹配度。宁可多提示，不可漏提示。"
    ),
    "growth": (
        "业务增长视角：你只关注价值——经营改善迹象、收入拐点、行业前景、"
        "额度与客户经营规模的适配性、产品对客户经营的支持作用。"
    ),
}


def debate_messages(perspective: str, product_name: str, slots: dict,
                    facts_text: str = "", experiences_text: str = "") -> list[dict]:
    """双视角辩论：单个视角对 Top1 推荐出具结构化意见。

    设计说明：
    - 输出 JSON 契约 {stance, points, suggested_caveats, score_adjust}：
      结构化意见才能进入裁决逻辑（stance=反对 触发 Top2 再评估），
      自由文本无法被机制消费——机制设计 > 模型能力；
    - PIT 条款 + "不得编造财务数据"：视角意见只能基于对话已提供信息与
      产品库静态数据，防止模型"脑补"客户财报；
    - 经验库注入：相似历史推荐作为参考上下文（收敛性 + 可复现性），
      但明确标注"仅供参考，不影响本次独立判断"，防锚定偏误；
    - 要点限 4 条、每条 30 字内：短输出难编造，且可直接进回复分区。
    """
    if perspective not in DEBATE_PERSPECTIVES:
        raise ValueError(f"未知辩论视角: {perspective!r}")
    system = (
        PERSONA + "\n\n"
        "你的任务：以指定视角评审一笔授信推荐，输出结构化意见（JSON）。\n"
        + DEBATE_PERSPECTIVES[perspective] + "\n"
        + PIT_CLAUSE + "\n"
        "不得编造客户的任何财务数据；只能就已知信息指出风险或价值，"
        "信息不足时把'待核实事项'写入 suggested_caveats。\n"
        "输出契约：只输出一行 JSON：{\"stance\": \"支持|谨慎支持|反对\", "
        "\"points\": [\"要点，每条30字内，最多4条\"], "
        "\"suggested_caveats\": [\"应提示客户的风险/待补充材料，最多3条\"], "
        "\"score_adjust\": 0.0}（评分微调建议，范围 -0.2 ~ 0.2，无建议给 0.0）。"
    )
    if perspective == "risk":
        pairs = [
            ('产品：极速信用贷；客户槽位：{"amount": 50000, "monthly_income": 4000, "purpose": "消费"}；已知事实：无；相似经验：无',
             '{"stance": "谨慎支持", "points": ["借款5万约为年收入1倍，偿付压力可控", "无抵押纯信用，依赖收入稳定性", "征信状况未披露"], "suggested_caveats": ["建议提供近6个月工资流水", "建议查询个人征信报告"], "score_adjust": -0.05}'),
        ]
    else:
        pairs = [
            ('产品：兴业经营贷；客户槽位：{"amount": 500000, "purpose": "进货", "occupation": "个体户"}；已知事实：无；相似经验：无',
             '{"stance": "支持", "points": ["进货属经营性需求，与产品定位契合", "个体户为目标客群", "50万额度在个体工商户经营场景内合理"], "suggested_caveats": [], "score_adjust": 0.05}'),
        ]
    user = (f"产品：{product_name}；客户槽位：{json.dumps(slots, ensure_ascii=False)}；"
            f"已知事实：{facts_text or '无'}；相似经验：{experiences_text or '无'}")
    return _msgs(system, pairs, user)
