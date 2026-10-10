"""LLM 客户端封装：OpenAI 兼容协议（Kimi / DeepSeek）+ MockLLM 确定性降级。

架构：

- OpenAICompatClient：纯 urllib 实现，不依赖 openai sdk，任何环境可 import；
  仅在实际调用时需要网络与 API Key。六个业务方法（意图/槽位/推荐理由/
  文案模板/合规复核/合规重写）的提示词统一来自 src/llm/prompts.py（单一事实来源），
  输出解析统一走“剥 fence → 找首尾 {} → 修复重试一次 → 确定性降级”的
  鲁棒管线；任何失败都降级到内置 MockLLM 的确定性逻辑，对话链路永不可崩。
- KimiClient / DeepSeekClient：同一协议的两个 provider 配置（base_url/模型/
  默认采样参数不同），构造签名与旧版 DeepSeekClient 保持兼容。
- MockLLM：无 Key 时的确定性替身 —— 意图分类走关键词评分、
  营销文案只产出“无数字模板”、槽位抽取复用规则通道，
  保证 demo 与单测在零外部依赖下完整跑通。
- get_llm()：provider 探测链 —— 显式 LLM_PROVIDER 优先；
  auto 模式下 DEEPSEEK_API_KEY → KIMI_API_KEY/MOONSHOT_API_KEY → Mock。
"""
from __future__ import annotations

import json
import re
import urllib.request
import urllib.error

from src.intent.labels import ALL_INTENTS, CODE_TO_LABEL, prompt_block  # noqa: F401  (prompt_block 经 prompts 模块复用)
from src.llm import prompts

# 企业称谓提取：贪婪匹配会把“帮我看看”等动词前缀吞进名称，需剥离
_COMPANY_MENTION_RE = re.compile(r"([一-龥A-Za-z0-9]{2,12}?)(?:那|这)?家(?:公司|企业)")
_LEADING_FILLERS = ("帮我看看", "帮我看下", "帮我", "帮忙", "看看", "看下", "看一看",
                    "查一下", "查查", "查看", "了解一下", "了解", "介绍一下", "介绍",
                    "我想看看", "我想", "我要", "想", "一下")


def _extract_company_mention(text: str) -> str | None:
    """从“帮我看看华创那家公司情况”中抽取关键称谓“华创”（原样保留，不臆造补全）。"""
    m = _COMPANY_MENTION_RE.search(text)
    if not m:
        return None
    name = m.group(1)
    changed = True
    while changed and len(name) > 2:
        changed = False
        for filler in _LEADING_FILLERS:
            if name.startswith(filler) and len(name) - len(filler) >= 2:
                name = name[len(filler):]
                changed = True
    return name or None


# 对话回复合规拦截后的通用安全话术（重写失败时的最终兜底；
# 顾问式口吻、不答非所问、引导客户补充信息或转人工）
SAFE_DIALOGUE_FALLBACK = (
    "很抱歉，刚才的回复未能通过行内合规校验。"
    "您可以告诉我资金用途、金额与期限，我会按银行规范重新为您解答；"
    "如需详细方案，也可以为您转接人工客户经理。"
)


class BaseLLM:
    """统一接口。is_mock 供各处做能力探测与降级判断；
    backend_name/model_name 供 /health 与日志暴露真实后端。"""

    is_mock = False
    backend_name = "base"
    model_name = ""

    def chat(self, messages: list[dict], temperature: float = 0.3, max_tokens: int = 1024) -> str:
        raise NotImplementedError

    def classify_intent(self, text: str) -> tuple[str, str]:
        """返回 (意图编码, 说明)。"""
        raise NotImplementedError

    def gen_copy_template(self, product_name: str, tone: str = "亲切专业") -> str:
        """生成营销文案【模板】：只允许 {} 槽位，禁止输出任何数字。"""
        raise NotImplementedError

    def explain_recommendation(self, product_name: str, slots: dict) -> str:
        raise NotImplementedError

    def extract_slots(self, text: str, schema: list[str]) -> dict:
        raise NotImplementedError

    def review_compliance(self, text: str) -> bool:
        """合规复核：True=通过，False=违规。"""
        raise NotImplementedError

    def rewrite_compliant(self, text: str, issues: list[str] | None = None) -> str:
        """对话回复的合规重写：保留业务信息与数值，去除违规表述。"""
        raise NotImplementedError

    def extract_site_actions(self, text: str, page: str | None = None) -> list[dict]:
        """模糊语义 → 网站动作列表；无动作返回 []，绝不影响对话主链路。"""
        raise NotImplementedError

    def debate_perspective(self, perspective: str, product_name: str, slots: dict,
                           facts_text: str = "", experiences_text: str = "") -> dict:
        """双视角辩论：单视角结构化意见
        {stance, points[], suggested_caveats[], score_adjust}。"""
        raise NotImplementedError


# ------------------------------------------------------------------ Mock

class MockLLM(BaseLLM):
    """确定性 Mock：演示与测试的事实标准。"""

    is_mock = True
    backend_name = "mock"
    model_name = ""

    # 关键词表按“优先级从高到低”排列，首个命中的意图胜出。
    # 这模拟了 Prompt 基线路由的行为 —— 稳定但粗糙（约七成准确率，
    # 见 docs/implementation-guide.md 第 2 节对 LoRA 方案的对比）。
    _INTENT_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
        ("HUMAN_AGENT", ("人工", "投诉", "客户经理", "真人")),
        ("COPYWRITING", ("文案", "朋友圈", "海报", "宣传语", "广告语", "话术")),
        ("RATE_QUERY", ("利率", "利息", "年化", "几厘", "多少厘", "费率")),
        ("CREDIT_RECOMMEND", ("推荐", "能申请", "可以申请", "帮我看看", "能批", "能贷", "匹配", "适合我")),
        ("LIMIT_QUERY", ("额度", "能贷多少", "提额", "最高多少")),
        ("REPAYMENT", ("还款", "月供", "等额", "先息后本", "提前还")),
        ("APPLY_PROCESS", ("怎么申请", "申请流程", "怎么办", "如何办理", "审批要多久", "流程")),
        ("MATERIALS", ("材料", "资料", "证明", "流水单")),
        ("PRODUCT_CONSULT", ("产品", "介绍", "有哪些", "了解一下", "区别", "消费贷", "经营贷", "房抵", "车贷")),
    ]

    def classify_intent(self, text: str) -> tuple[str, str]:
        for code, keywords in self._INTENT_KEYWORDS:
            hit = next((k for k in keywords if k in text), None)
            if hit:
                return code, f"mock: 命中关键词“{hit}”"
        return "CHITCHAT", "mock: 未命中业务关键词，按闲聊处理"

    def gen_copy_template(self, product_name: str, tone: str = "亲切专业") -> str:
        # 关键纪律：模板中不出现任何数字，数值槽位由代码填充
        return (
            f"【{{product_name}}】您的{{category}}好帮手：最高可借{{max_amount}}，"
            f"年化利率低至{{rate_min}}起，期限{{min_term}}-{{max_term}}个月灵活可选，"
            f"最快{{approval_hours}}小时完成审批。线上申请，流程透明，{tone}服务全程陪伴。"
        )

    def explain_recommendation(self, product_name: str, slots: dict) -> str:
        parts = []
        if slots.get("purpose"):
            parts.append(f"用途“{slots['purpose']}”在准入范围内")
        if slots.get("amount"):
            parts.append(f"额度覆盖{slots['amount'] / 10000:g}万需求")
        return f"推荐{product_name}：" + "，".join(parts) if parts else f"推荐{product_name}"

    def extract_slots(self, text: str, schema: list[str]) -> dict:
        from src.recommend.slots import extract_slots_rules

        return extract_slots_rules(text).filled()

    def review_compliance(self, text: str) -> bool:
        from src.compliance.regex_guard import is_compliant

        return is_compliant(text)

    def rewrite_compliant(self, text: str, issues: list[str] | None = None) -> str:
        # 离线确定性兜底：通用安全话术（绝不换成营销模板，答非所问）
        return SAFE_DIALOGUE_FALLBACK

    def extract_site_actions(self, text: str, page: str | None = None) -> list[dict]:
        """离线降级：关键词规则生成动作（确定性、与提示词 few-shot 对齐）。"""
        t = text
        # 1) 文案生成（含产品名/渠道提取）
        if any(k in t for k in ("朋友圈", "文案", "宣传", "海报", "话术")):
            from src.recommend.catalog import get_catalog

            params: dict = {}
            name = next((p.name for p in get_catalog() if p.name in t), None)
            if name:
                params["product_name"] = name
            if "朋友圈" in t:
                params["channel"] = "朋友圈"
            return [{"type": "generate_copy", "params": params}]
        # 2) 授信推荐
        if any(k in t for k in ("推荐", "能贷", "能批", "能申请")):
            return [{"type": "recommend", "params": {}}]
        # 3) 看板数据
        if any(k in t for k in ("最近业务", "业务数据", "业务怎么样", "看板", "统计", "今日数据")):
            return [{"type": "show_stats", "params": {}}]
        # 4) 查看某企业详情（“华创那家公司情况” → view_customer{华创}）
        mention = _extract_company_mention(t)
        if mention and any(k in t for k in ("看看", "情况", "怎么样", "详情", "查一下", "了解")):
            return [{"type": "view_customer", "params": {"name": mention}}]
        # 5) 客户筛选
        if any(k in t for k in ("客户", "公司", "企业")) and any(k in t for k in ("筛选", "找", "搜", "有没有", "哪些")):
            if mention:
                return [{"type": "search_customer", "params": {"keyword": mention}}]
            ind = re.search(r"(制造业|物流|贸易|生物|建筑|餐饮|科技)", t)
            if ind:
                return [{"type": "search_customer", "params": {"keyword": ind.group(1)}}]
        # 6) 查看产品（产品名命中且非文案场景）
        from src.recommend.catalog import get_catalog

        pname = next((p.name for p in get_catalog() if p.name in t), None)
        if pname and any(k in t for k in ("看看", "介绍", "详情", "了解", "怎么样")):
            return [{"type": "open_product", "params": {"name": pname}}]
        # 7) 页面导航
        nav = [("看板", "/dashboard"), ("客户页", "/customer"), ("产品页", "/product"),
               ("推荐记录", "/recommend"), ("文案页", "/copy"), ("智能顾问", "/chat"),
               ("个人中心", "/profile")]
        for kw, path in nav:
            if kw in t and any(k in t for k in ("打开", "去", "跳", "进入", "到")):
                return [{"type": "navigate", "params": {"path": path}}]
        return []

    def chat(self, messages: list[dict], temperature: float = 0.3, max_tokens: int = 1024) -> str:
        content = messages[-1]["content"] if messages else ""
        if "意图" in content:
            code, _ = self.classify_intent(content)
            return code
        if "模板" in content or "文案" in content:
            return self.gen_copy_template("{product_name}")
        return "您好，我是智能信贷助手，可以为您介绍产品、查询利率、推荐方案或生成合规营销文案。"

    def debate_perspective(self, perspective: str, product_name: str, slots: dict,
                           facts_text: str = "", experiences_text: str = "") -> dict:
        """离线降级：基于槽位规则的模板化视角意见（确定性、可解释、可测试）。

        风险视角的偿债比规则与 engine.detect_hard_issues 口径一致——
        离线模式下"模型意见"与"规则硬伤"天然同源，不会出现矛盾裁决。
        """
        if perspective == "risk":
            stance, points, caveats = "谨慎支持", [], []
            income, amount = slots.get("monthly_income"), slots.get("amount")
            if income and amount:
                ratio = amount / max(income * 12, 1)
                if ratio > 3:
                    stance = "反对"
                    points.append(f"借款{amount / 10000:g}万约为年收入的{ratio:.1f}倍，偿付压力显著")
                    caveats.append("建议降低申请额度或补充经营性现金流证明")
                else:
                    points.append(f"借款{amount / 10000:g}万约为年收入的{ratio:.1f}倍，处于可控区间")
            else:
                points.append("客户未提供收入或经营流水，偿债能力待核实")
                caveats.append("建议补充近6个月经营流水或纳税记录")
            if not slots.get("credit_status"):
                points.append("征信状况未在对话中披露")
                caveats.append("建议查询企业征信后再核定最终额度")
            return {"stance": stance, "points": points,
                    "suggested_caveats": caveats, "score_adjust": 0.0}
        # 业务增长视角
        points = []
        if slots.get("purpose") in ("经营", "周转", "进货"):
            points.append(f"用途“{slots['purpose']}”属经营性需求，与产品定位契合")
        if slots.get("occupation"):
            points.append(f"客户身份为{slots['occupation']}，属目标客群")
        if slots.get("amount"):
            points.append(f"额度需求{slots['amount'] / 10000:g}万在经营场景内具合理性")
        if not points:
            points.append(f"客户场景与{product_name}定位总体匹配")
        return {"stance": "支持", "points": points,
                "suggested_caveats": [], "score_adjust": 0.0}


# ------------------------------------------------------------------ 鲁棒解析工具

def _strip_fence(text: str) -> str:
    """剥掉 markdown 代码围栏（``` 或 ```json 行）。"""
    lines = [ln for ln in text.strip().splitlines() if not ln.strip().startswith("```")]
    return "\n".join(lines).strip()


def _loose_json(text: str) -> dict:
    """宽松 JSON 对象解析：剥 fence → 取首个 { 到末个 } → json.loads。

    任何一步失败抛 ValueError，由调用方决定重试或降级。
    """
    cleaned = _strip_fence(text)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError(f"输出中找不到 JSON 对象: {text[:80]!r}")
    try:
        obj = json.loads(cleaned[start: end + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 解析失败: {e}") from e
    if not isinstance(obj, dict):
        raise ValueError(f"JSON 顶层不是对象: {type(obj).__name__}")
    return obj


# 槽位键 → 目标类型（与 src/recommend/slots.py 的 SlotSet 对齐）
_SLOT_TYPES: dict[str, type] = {
    "amount": float, "monthly_income": float,
    "term_months": int, "age": int, "credit_score": int,
    "purpose": str, "occupation": str, "credit_status": str,
}


def _sanitize_slots(obj: dict, schema: list[str]) -> dict:
    """槽位第二道闸：schema 白名单 + 类型强制转换。

    模型可能返回 schema 之外的键、字符串数字（"200000"）、带单位文本
    （"200万"）—— 前两者可救（转换），后者丢弃，绝不把脏数据放进 SlotSet
    （脏类型会在推荐评分的算术里炸掉整条链路）。
    """
    out: dict = {}
    for k, v in obj.items():
        if k not in schema or v is None:
            continue
        t = _SLOT_TYPES.get(k, str)
        try:
            if t is str:
                s = str(v).strip()
                if s:
                    out[k] = s
            elif t is int:
                out[k] = int(float(v))
            else:
                out[k] = float(v)
        except (TypeError, ValueError):
            continue  # 无法转换的值直接丢弃（如 "200万" 含单位文本）
    return out


# 网站动作白名单：type → 必填参数（与前端执行器一一对应）
_SITE_ACTION_REQUIRED: dict[str, tuple] = {
    "navigate": ("path",),
    "search_customer": ("keyword",),
    "view_customer": ("name",),
    "open_product": ("name",),
    "generate_copy": (),
    "show_stats": (),
    "recommend": (),
    "none": (),
}
_SITE_NAV_PATHS = frozenset(
    {"/dashboard", "/customer", "/product", "/recommend", "/copy", "/chat", "/profile"}
)


def _sanitize_site_actions(obj: dict) -> list[dict]:
    """动作 JSON 第二道闸：白名单 + 必填参数 + 路径白名单。

    - 非白名单动作直接丢弃（防模型“幻觉动作”）；
    - 必填参数缺失/空、navigate 路径越白名单 → 降级为 none；
    - none 归一化为“无动作”（返回空数组），最多保留 2 个动作；
    - 结构不合法（无 actions 数组）抛 ValueError，由 _ask 修复重试。
    """
    raw = obj.get("actions") if isinstance(obj, dict) else None
    if not isinstance(raw, list):
        raise ValueError(f"动作输出缺少 actions 数组: {str(obj)[:80]!r}")
    out: list[dict] = []
    for item in raw[:4]:
        if not isinstance(item, dict):
            continue
        t = str(item.get("type") or "").strip()
        if t not in _SITE_ACTION_REQUIRED:
            continue  # 非白名单丢弃
        params = item.get("params")
        params = {k: str(v).strip() for k, v in (params.items() if isinstance(params, dict) else [])
                  if v is not None and str(v).strip()}
        if t == "navigate" and params.get("path") not in _SITE_NAV_PATHS:
            t, params = "none", {}
        elif any(not params.get(k) for k in _SITE_ACTION_REQUIRED[t]):
            t, params = "none", {}  # 参数缺失降级
        if t == "none":
            continue
        out.append({"type": t, "params": params})
        if len(out) >= 2:
            break
    return out


# ------------------------------------------------------------------ 辩论意见解析

_DEBATE_STANCES = ("支持", "谨慎支持", "反对")


def _sanitize_debate(obj: dict) -> dict:
    """辩论意见 JSON 第二道闸（与 _sanitize_site_actions 同纪律）。

    - stance 越出三值枚举 → 归一"谨慎支持"（中间态，不误触发硬伤）；
    - points/suggested_caveats 只保留字符串、限量限长（防模型长篇编造）；
    - score_adjust 钳制在 [-0.2, 0.2]，非法值归 0；
    - 结构不合法（非 dict）抛 ValueError，由 _ask 修复重试。
    """
    if not isinstance(obj, dict):
        raise ValueError(f"辩论输出不是 JSON 对象: {str(obj)[:80]!r}")
    stance = str(obj.get("stance") or "").strip()
    if stance not in _DEBATE_STANCES:
        stance = "谨慎支持"

    def _str_list(key: str, limit: int, max_len: int) -> list[str]:
        raw = obj.get(key)
        if not isinstance(raw, list):
            return []
        return [str(x).strip()[:max_len] for x in raw
                if isinstance(x, (str, int, float)) and str(x).strip()][:limit]

    try:
        adjust = float(obj.get("score_adjust") or 0.0)
    except (TypeError, ValueError):
        adjust = 0.0
    adjust = max(-0.2, min(0.2, adjust))
    return {
        "stance": stance,
        "points": _str_list("points", 4, 60),
        "suggested_caveats": _str_list("suggested_caveats", 3, 60),
        "score_adjust": round(adjust, 4),
    }


# ------------------------------------------------------------------ OpenAI 兼容客户端

class OpenAICompatClient(BaseLLM):
    """OpenAI 兼容协议客户端（urllib 零依赖），六个业务方法共用一套
    “提示词 → 调用 → 解析 → 重试 → 降级”管线。

    降级语义：网络故障、HTTP 错误、空响应、解析屡败 —— 一律降级到
    fallback（默认 MockLLM）的对应确定性方法，并在外层调用方可见的
    detail/返回值上与 Mock 行为保持一致，对话主链路永不因 LLM 故障崩溃。
    """

    backend_name = "openai-compat"

    def __init__(self, api_key: str, base_url: str, model: str,
                 timeout: float = 45.0, temperature: float = 1.0,
                 max_tokens: int = 2048, fallback: BaseLLM | None = None) -> None:
        self.api_key = api_key
        # base_url 规范化：部署环境（如网关代理）常省略版本段
        # （https://agent-gw.kimi.com/coding/ → .../coding/v1），缺则补 /v1
        base = base_url.rstrip("/")
        if not re.search(r"/v\d+[a-z0-9-]*$", base, re.IGNORECASE):
            base += "/v1"
        self.base_url = base
        self.model = model
        self.model_name = model
        self.timeout = timeout
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._fallback = fallback or MockLLM()

    # ---- 网络触点（唯一）：测试中用脚本化子类覆盖此方法即可全离线 ----

    def _post(self, messages: list[dict], temperature: float, max_tokens: int) -> str:
        """发起一次 chat/completions 调用，返回 content 文本。

        失败抛 RuntimeError。空 content 也视为失败（reasoning 模型在
        max_tokens 不足时会把预算耗尽于思考、content 为空）。
        """
        req = urllib.request.Request(
            url=f"{self.base_url}/chat/completions",
            data=json.dumps({
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "ignore")[:200]
            raise RuntimeError(f"{self.backend_name} HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"{self.backend_name} 网络故障: {e}") from e
        choices = body.get("choices") or []
        content = ((choices[0].get("message") or {}).get("content") or "") if choices else ""
        if not content.strip():
            finish = choices[0].get("finish_reason") if choices else "no-choices"
            raise RuntimeError(f"{self.backend_name} 空响应（finish_reason={finish}）")
        return content.strip()

    def chat(self, messages: list[dict], temperature: float | None = None,
             max_tokens: int | None = None) -> str:
        return self._post(
            messages,
            self.temperature if temperature is None else temperature,
            max_tokens or self.max_tokens,
        )

    # ---- 调用 + 解析 + 修复重试 ----

    def _ask(self, messages: list[dict], parse, max_tokens: int, retries: int = 1):
        """调用并把原始输出交给 parse；失败时重试一次，仍失败抛 RuntimeError。

        两类可重试失败，对应两种修复策略：
        1) 空响应（reasoning 模型把 token 预算耗尽于思考、content 为空）：
           重试时【翻倍 max_tokens】（上限 4096），不重发消息；
        2) 解析失败（输出格式不符）：把模型的坏输出和 REPAIR_HINT 追加为
           新的一轮，让模型在自己输出的上下文里纠错，比原样重发成功率高。

        网络/HTTP 故障不可重试（立即抛出让调用方走确定性降级）。
        """
        attempt = list(messages)
        budget = max_tokens
        last_err: Exception | None = None
        for i in range(retries + 1):
            try:
                out = self._post(attempt, temperature=self.temperature, max_tokens=budget)
            except RuntimeError as e:
                if "空响应" in str(e) and i < retries:
                    last_err = e
                    budget = min(budget * 2, 4096)
                    continue
                raise
            try:
                return parse(out)
            except ValueError as e:
                last_err = e
                attempt = messages + [
                    {"role": "assistant", "content": out},
                    {"role": "user", "content": prompts.REPAIR_HINT},
                ]
        raise RuntimeError(f"输出解析失败（已重试 {retries} 次）: {last_err}")

    # ---- 五层业务方法 ----

    def classify_intent(self, text: str) -> tuple[str, str]:
        def parse(out: str) -> str:
            try:
                code = str(_loose_json(out).get("intent", ""))
            except ValueError:
                m = re.search(r"[A-Z_]{3,}", out)  # 兼容裸标签输出
                code = m.group(0) if m else ""
            if code in CODE_TO_LABEL:
                return code
            raise ValueError(f"非法意图输出: {out[:80]!r}")

        try:
            code = self._ask(prompts.intent_messages(text), parse, max_tokens=1024)
            return code, f"{self.backend_name}: prompt 路由"
        except Exception as e:
            code, detail = self._fallback.classify_intent(text)
            return code, f"{self.backend_name} 失败降级（{type(e).__name__}）；{detail}"

    def extract_slots(self, text: str, schema: list[str]) -> dict:
        def parse(out: str) -> dict:
            return _sanitize_slots(_loose_json(out), schema)

        try:
            return self._ask(prompts.slot_messages(text, schema), parse, max_tokens=1536)
        except Exception:
            return {}  # 规则通道已先行抽取，LLM 失败=不补缺，无损降级

    def explain_recommendation(self, product_name: str, slots: dict) -> str:
        def parse(out: str) -> str:
            line = _strip_fence(out).strip().strip('"“”')
            line = line.splitlines()[0].strip() if line else ""
            if not line:
                raise ValueError("空推荐理由")
            return line[:120]

        try:
            return self._ask(prompts.reply_messages(product_name, slots), parse, max_tokens=1280)
        except Exception:
            return self._fallback.explain_recommendation(product_name, slots)

    def gen_copy_template(self, product_name: str, tone: str = "亲切专业") -> str:
        def parse(out: str) -> str:
            template = _strip_fence(out).strip()
            if not template or "{" not in template:
                raise ValueError(f"模板为空或缺少槽位: {out[:80]!r}")
            return template

        try:
            return self._ask(prompts.copy_messages(product_name, tone), parse, max_tokens=2048)
        except Exception:
            # 失败降级到内置安全模板（游离数字拦截由调用方 template_fill 把关）
            return self._fallback.gen_copy_template(product_name, tone)

    def review_compliance(self, text: str) -> bool:
        def parse(out: str) -> bool:
            try:
                verdict = str(_loose_json(out).get("verdict", ""))
            except ValueError:
                verdict = out  # 兼容裸 PASS/BLOCK 输出
            v = verdict.strip().upper()
            if "BLOCK" in v:
                return False
            if "PASS" in v:
                return True
            raise ValueError(f"非法审核输出: {out[:80]!r}")

        try:
            return self._ask(prompts.compliance_messages(text), parse, max_tokens=1280)
        except Exception:
            return self._fallback.review_compliance(text)  # 降级到正则硬拦截结论

    def rewrite_compliant(self, text: str, issues: list[str] | None = None) -> str:
        def parse(out: str) -> str:
            rewritten = _strip_fence(out).strip()
            if len(rewritten) < 4:
                raise ValueError(f"重写结果为空或过短: {out[:60]!r}")
            return rewritten

        try:
            return self._ask(prompts.rewrite_messages(text, issues), parse, max_tokens=2048)
        except Exception:
            # 重写失败 → 通用安全话术（对话兜底纪律：不答非所问）
            return self._fallback.rewrite_compliant(text, issues)

    def extract_site_actions(self, text: str, page: str | None = None) -> list[dict]:
        def parse(out: str) -> list[dict]:
            return _sanitize_site_actions(_loose_json(out))

        try:
            return self._ask(prompts.site_action_messages(text, page), parse, max_tokens=1024)
        except Exception:
            return []  # 动作抽取失败不影响对话主链路（等价于纯对话）

    def debate_perspective(self, perspective: str, product_name: str, slots: dict,
                           facts_text: str = "", experiences_text: str = "") -> dict:
        def parse(out: str) -> dict:
            return _sanitize_debate(_loose_json(out))

        try:
            return self._ask(
                prompts.debate_messages(perspective, product_name, slots,
                                        facts_text, experiences_text),
                parse, max_tokens=1536)
        except Exception:
            # 辩论意见失败降级到规则模板意见（离线同源口径，机制不缺席）
            return self._fallback.debate_perspective(
                perspective, product_name, slots, facts_text, experiences_text)


# ------------------------------------------------------------------ 两个 provider

class DeepSeekClient(OpenAICompatClient):
    """DeepSeek（OpenAI 兼容）。默认采样参数保持旧版行为（低温 0.3）。"""

    backend_name = "deepseek"

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com/v1",
                 model: str = "deepseek-chat", timeout: float = 30.0,
                 temperature: float = 0.3, max_tokens: int = 1024,
                 fallback: BaseLLM | None = None) -> None:
        super().__init__(api_key, base_url, model, timeout=timeout,
                         temperature=temperature, max_tokens=max_tokens, fallback=fallback)


class KimiClient(OpenAICompatClient):
    """Kimi（Moonshot，OpenAI 兼容）。

    默认端点为 Kimi for Coding（api.kimi.com/coding/v1），默认模型
    kimi-for-coding-highspeed（reasoning 模型中延迟最低的一档，面试/演示
    场景单轮耗时约为 kimi-for-coding 的一半；追求极致稳定可换回
    kimi-for-coding）。该端点仅允许 temperature=1，故默认采样参数与
    DeepSeek 不同；使用公共端点（api.moonshot.cn）时可通过
    KIMI_BASE_URL / KIMI_MODEL / LLM_TEMPERATURE 覆盖。
    """

    backend_name = "kimi"

    def __init__(self, api_key: str, base_url: str = "https://api.kimi.com/coding/v1",
                 model: str = "kimi-for-coding-highspeed", timeout: float = 45.0,
                 temperature: float = 1.0, max_tokens: int = 2048,
                 fallback: BaseLLM | None = None) -> None:
        super().__init__(api_key, base_url, model, timeout=timeout,
                         temperature=temperature, max_tokens=max_tokens, fallback=fallback)


# ------------------------------------------------------------------ 工厂

def get_llm(settings=None) -> BaseLLM:
    """provider 探测链：显式 LLM_PROVIDER > auto 自动探测 > Mock。

    auto 顺序：DEEPSEEK_API_KEY → KIMI_API_KEY/MOONSHOT_API_KEY → MockLLM；
    保证任何环境（含零 key 的演示/测试环境）都可运行。
    """
    if settings is None:
        from configs.settings import get_settings

        settings = get_settings()

    provider = (getattr(settings, "llm_provider", "") or "auto").strip().lower()
    kimi_key = (getattr(settings, "kimi_api_key", "")
                or getattr(settings, "moonshot_api_key", ""))

    def _kimi() -> BaseLLM:
        if not kimi_key:
            return MockLLM()
        return KimiClient(
            api_key=kimi_key,
            base_url=getattr(settings, "kimi_base_url", "") or "https://api.kimi.com/coding/v1",
            model=getattr(settings, "kimi_model", "") or "kimi-for-coding-highspeed",
            timeout=getattr(settings, "llm_timeout", 45.0),
            temperature=getattr(settings, "llm_temperature", 1.0),
            max_tokens=getattr(settings, "llm_max_tokens", 2048),
        )

    def _deepseek() -> BaseLLM:
        if not settings.deepseek_api_key:
            return MockLLM()
        return DeepSeekClient(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
        )

    if provider == "mock":
        return MockLLM()
    if provider in ("kimi", "moonshot"):
        return _kimi()
    if provider == "deepseek":
        return _deepseek()
    # auto
    if settings.deepseek_api_key:
        return _deepseek()
    if kimi_key:
        return _kimi()
    return MockLLM()
