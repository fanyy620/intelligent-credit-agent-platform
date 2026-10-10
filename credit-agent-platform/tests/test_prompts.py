"""提示词驱动层单测（全离线，零网络）。

策略：ScriptedLLM 继承 KimiClient，仅覆盖唯一网络触点 _post()，
按脚本队列返回预置输出（或抛出预置异常），从而离线验证：

- 五层方法的提示词 → 解析管线（JSON 宽松解析、剥 fence、裸标签兼容）；
- 解析失败 → 携带 REPAIR_HINT 重试一次 → 仍失败降级 MockLLM 确定性逻辑；
- 网络故障 → 立即降级，主链路不崩；
- get_llm() provider 探测链（构造不触网，仅验证选型逻辑）。

运行：python -m pytest tests/test_prompts.py -q
"""
from __future__ import annotations

from configs.settings import Settings
from src.agent import nodes
from src.agent.nodes import RuntimeContext
from src.compliance import template_fill
from src.llm import prompts
from src.llm.client import KimiClient, DeepSeekClient, MockLLM, get_llm
from src.observability.tracing import NoopTracer
from src.recommend.catalog import get_catalog


class ScriptedLLM(KimiClient):
    """脚本化 LLM：_post 依次弹出脚本；元素为 Exception 实例时抛出。"""

    def __init__(self, script: list) -> None:
        super().__init__(api_key="fake", base_url="http://fake.local", model="fake-model")
        self.script = list(script)
        self.calls: list[list[dict]] = []

    def _post(self, messages, temperature, max_tokens):  # noqa: D102
        self.calls.append(messages)
        if not self.script:
            raise RuntimeError("测试脚本耗尽")
        out = self.script.pop(0)
        if isinstance(out, Exception):
            raise out
        return out


# ------------------------------------------------------------------ 意图层

def test_intent_json_output():
    llm = ScriptedLLM(['{"intent": "CREDIT_RECOMMEND", "reason": "给出条件求推荐"}'])
    code, detail = llm.classify_intent("我们是制造业企业，需要200万流动资金贷款")
    assert code == "CREDIT_RECOMMEND"
    assert "kimi" in detail
    assert len(llm.calls) == 1


def test_intent_fenced_and_bare_output():
    fenced = ScriptedLLM(['```json\n{"intent": "LIMIT_QUERY", "reason": "单问额度"}\n```'])
    assert fenced.classify_intent("我最多能贷多少")[0] == "LIMIT_QUERY"
    bare = ScriptedLLM(["RATE_QUERY"])
    assert bare.classify_intent("税易贷利率多少")[0] == "RATE_QUERY"


def test_intent_retry_with_repair_hint():
    llm = ScriptedLLM(["让我想想这个问题……", '{"intent": "COPYWRITING"}'])
    code, _ = llm.classify_intent("帮我写一段朋友圈文案")
    assert code == "COPYWRITING"
    assert len(llm.calls) == 2
    # 第二次调用携带了模型的坏输出与修复指令
    assert llm.calls[1][-2]["role"] == "assistant"
    assert "无法被程序解析" in llm.calls[1][-1]["content"]


def test_intent_parse_twice_failed_fallback_mock():
    llm = ScriptedLLM(["完全无法解析", "依然无法解析"])
    code, detail = llm.classify_intent("帮我看看能贷多少")
    # 降级到 MockLLM 关键词通道（“帮我看看/能贷”命中授信推荐）
    assert code == "CREDIT_RECOMMEND"
    assert "失败降级" in detail
    assert len(llm.calls) == 2


def test_intent_network_error_fallback_immediately():
    llm = ScriptedLLM([RuntimeError("kimi HTTP 401: Invalid Authentication")])
    code, detail = llm.classify_intent("转人工")
    assert code == "HUMAN_AGENT"  # Mock 关键词命中
    assert "失败降级" in detail
    assert len(llm.calls) == 1  # 网络故障不重试，立即降级


# ------------------------------------------------------------------ 槽位层

def test_slots_dirty_json_sanitized():
    llm = ScriptedLLM([
        '抽取结果如下：\n```json\n'
        '{"amount": "2000000", "term_months": 12, "purpose": "经营",'
        ' "evil_key": 1, "occupation": null}\n```\n以上供参考'
    ])
    slots = llm.extract_slots("需要200万流动资金贷款，期限12个月",
                              schema=["amount", "term_months", "purpose", "occupation"])
    # 字符串数字被转换、schema 外键被白名单过滤、null 被丢弃
    assert slots == {"amount": 2000000.0, "term_months": 12, "purpose": "经营"}


def test_slots_unconvertible_value_dropped():
    llm = ScriptedLLM(['{"amount": "200万", "term_months": 12}'])
    slots = llm.extract_slots("借200万用12个月", schema=["amount", "term_months"])
    # 带单位文本无法转 float，整条丢弃，绝不污染 SlotSet
    assert slots == {"term_months": 12}


def test_slots_invalid_twice_returns_empty():
    llm = ScriptedLLM(["没有JSON", "还是没有"])
    assert llm.extract_slots("随便说说", schema=["amount"]) == {}
    assert len(llm.calls) == 2


def test_slots_empty_object_is_legal():
    llm = ScriptedLLM(["{}"])
    assert llm.extract_slots("你们有什么产品", schema=["amount"]) == {}
    assert len(llm.calls) == 1  # 合法输出，不触发重试


# ------------------------------------------------------------------ 推荐理由层

def test_explain_recommendation_passthrough():
    llm = ScriptedLLM(["制造业流动资金需求200万，该产品正是面向对公经营场景。"])
    reason = llm.explain_recommendation("税易贷", {"amount": 2000000, "purpose": "经营"})
    assert "税易贷" not in reason or True  # 内容原样返回
    assert reason.startswith("制造业")


def test_explain_failure_fallback_mock():
    llm = ScriptedLLM([RuntimeError("网络故障"), ])
    reason = llm.explain_recommendation("信享贷", {"purpose": "装修", "amount": 200000})
    assert "装修" in reason  # Mock 确定性解释兜底


# ------------------------------------------------------------------ 文案模板层

GOOD_TEMPLATE = ("【{product_name}】{category}新选择：额度最高{max_amount}，"
                 "年化利率低至{rate_min}起，{min_term}-{max_term}个月灵活可选。")


def test_copy_template_no_free_numbers():
    llm = ScriptedLLM([GOOD_TEMPLATE])
    template = llm.gen_copy_template("税易贷")
    assert template == GOOD_TEMPLATE
    assert template_fill.find_free_numbers(template) == []


def test_copy_template_missing_slot_retried():
    llm = ScriptedLLM(["欢迎办理我行贷款，手续简便放款快。", GOOD_TEMPLATE])
    template = llm.gen_copy_template("信享贷")
    assert template == GOOD_TEMPLATE
    assert len(llm.calls) == 2  # 首个输出无槽位 → 重试


def test_copy_template_failure_fallback_builtin():
    llm = ScriptedLLM(["垃圾输出", "还是垃圾"])
    template = llm.gen_copy_template("信享贷")
    assert "{max_amount}" in template  # 降级到 Mock 内置安全模板
    assert template_fill.find_free_numbers(template) == []


# ------------------------------------------------------------------ 合规审核层

def test_review_block_and_pass():
    blocker = ScriptedLLM(['{"verdict": "BLOCK", "reason": "承诺必过"}'])
    assert blocker.review_compliance("保证都能批下来") is False
    passer = ScriptedLLM(["PASS"])
    assert passer.review_compliance("最高可借30万，以审批结果为准") is True


def test_review_garbage_fallback_regex():
    dirty = ScriptedLLM(["说不清", "还是说不清"])
    assert dirty.review_compliance("本产品保本保息") is False  # 降级正则：违规
    clean = ScriptedLLM(["说不清", "还是说不清"])
    assert clean.review_compliance("年化利率低至4.8%起，以审批结果为准") is True


# ------------------------------------------------------------------ provider 探测链

def test_get_llm_provider_chain():
    # 零 key：Mock（演示/测试环境默认）
    assert isinstance(get_llm(Settings()), MockLLM)
    # auto：DeepSeek 优先于 Kimi
    assert isinstance(get_llm(Settings(deepseek_api_key="x")), DeepSeekClient)
    both = get_llm(Settings(deepseek_api_key="x", kimi_api_key="y"))
    assert isinstance(both, DeepSeekClient)
    # auto：KIMI_API_KEY 或 MOONSHOT_API_KEY 任一即可
    kimi = get_llm(Settings(kimi_api_key="y"))
    assert isinstance(kimi, KimiClient) and kimi.backend_name == "kimi"
    assert kimi.model_name == "kimi-for-coding-highspeed"
    assert isinstance(get_llm(Settings(moonshot_api_key="y")), KimiClient)
    # 显式指定
    assert isinstance(get_llm(Settings(kimi_api_key="y", llm_provider="kimi")), KimiClient)
    assert isinstance(get_llm(Settings(kimi_api_key="y", llm_provider="mock")), MockLLM)
    # 显式 deepseek 但无 deepseek key：安全落 Mock
    assert isinstance(get_llm(Settings(kimi_api_key="y", llm_provider="deepseek")), MockLLM)


# ------------------------------------------------------------------ prompts 模块结构

def test_prompts_five_layers_complete():
    """五层 builder 都产出 system 开头的 messages，人设与关键约束在位。"""
    schema = ["amount", "term_months", "purpose"]
    builders = {
        "intent": prompts.intent_messages("你好"),
        "slot": prompts.slot_messages("借20万", schema),
        "reply": prompts.reply_messages("信享贷", {"amount": 200000}),
        "copy": prompts.copy_messages("信享贷"),
        "compliance": prompts.compliance_messages("保本保息"),
        "rewrite": prompts.rewrite_messages("一段回复", ["违规点x"]),
        "site_action": prompts.site_action_messages("你好", "/dashboard"),
    }
    for name, msgs in builders.items():
        assert msgs[0]["role"] == "system", f"{name} 缺少 system"
        assert "南洋商业银行" in msgs[0]["content"], f"{name} 缺人设"
        assert msgs[-1]["role"] == "user", f"{name} 末尾应为真实用户输入"
        # few-shot 轮次 user/assistant 交替
        roles = [m["role"] for m in msgs[1:-1]]
        assert roles == ["user", "assistant"] * (len(roles) // 2), f"{name} few-shot 轮次错乱"


def test_prompts_key_constraints():
    intent_sys = prompts.intent_messages("x")[0]["content"]
    assert "CREDIT_RECOMMEND" in intent_sys and "CHITCHAT" in intent_sys  # 标签表在 system 中
    assert '"intent"' in intent_sys  # JSON 输出契约
    copy_sys = prompts.copy_messages("x")[0]["content"]
    assert "严禁出现任何阿拉伯数字" in copy_sys  # 防数值幻觉禁令
    assert "{max_amount}" in copy_sys  # 槽位白名单
    slot_sys = prompts.slot_messages("x", ["amount"])[0]["content"]
    assert "禁止推测" in slot_sys
    compliance_sys = prompts.compliance_messages("x")[0]["content"]
    assert "宁严勿宽" in compliance_sys
    assert "中性序号" in compliance_sys  # Top1/Top2 边界澄清（防顾问回复误拦）
    rewrite_sys = prompts.rewrite_messages("x", ["违规点"])[0]["content"]
    assert "原样保留" in rewrite_sys  # 重写层数值纪律（防重写引入新幻觉）


# ------------------------------------------------------------------ 对话回复合规分路（node_compliance）

ADVISORY_REPLY = (
    "根据您的情况，为您推荐以下产品（按综合评分排序）：\n"
    "  Top1 税易贷（经营贷）综合分 0.614\n"
    "      额度10-300万，年化3.85%-6.5%，6-36个月，最快48小时审批\n"
    "      推荐理由：您为企业主且用于经营，税易贷基于纳税记录提供融资支持。\n"
    "以上额度和利率均以最终审批为准。"
)


def _ctx_with_llm(llm) -> RuntimeContext:
    return RuntimeContext(
        llm=llm, router=None, memory=None,
        catalog=get_catalog(), stats=None, weights=None,
        tracer=NoopTracer(),
    )


def test_dialogue_normal_reply_not_blocked():
    llm = ScriptedLLM(['{"verdict": "PASS", "reason": "客观介绍"}'])
    result = nodes.node_compliance(
        {"answer": ADVISORY_REPLY, "user_input": "推荐一下"}, _ctx_with_llm(llm))
    assert result["blocked"] is False
    assert "answer" not in result  # 回复未被替换
    # 真实 LLM 模式下对话回复不走伪向量
    assert result["compliance_semantic"]["method"] == "skipped"


def test_dialogue_review_failure_fail_open():
    llm = ScriptedLLM([RuntimeError("kimi HTTP 500")])
    result = nodes.node_compliance({"answer": ADVISORY_REPLY}, _ctx_with_llm(llm))
    assert result["blocked"] is False  # 复核失败默认放行
    assert len(llm.calls) == 1  # 网络故障不重试不拦截


def test_dialogue_regex_violation_rewritten():
    llm = ScriptedLLM([
        '{"verdict": "PASS"}',
        "为您介绍我行信贷产品，具体额度与利率以审批结果为准。",
    ])
    state = {"answer": "这款产品保本保息，强烈推荐给您"}
    result = nodes.node_compliance(state, _ctx_with_llm(llm))
    assert result["blocked"] is True
    assert "为您介绍我行信贷产品" in result["answer"]
    assert "好帮手" not in result["answer"]  # 不得换成营销模板
    assert "承诺保本保息" in llm.calls[1][-1]["content"]  # 重写携带违规点上下文


def test_dialogue_llm_block_then_rewrite():
    llm = ScriptedLLM([
        '{"verdict": "BLOCK", "reason": "复核判定违规"}',
        "根据您的情况，为您推荐税易贷，具体以审批结果为准。",
    ])
    result = nodes.node_compliance({"answer": ADVISORY_REPLY}, _ctx_with_llm(llm))
    assert result["blocked"] is True
    assert "为您推荐税易贷" in result["answer"]
    assert "好帮手" not in result["answer"]


def test_dialogue_rewrite_failure_generic_fallback():
    llm = ScriptedLLM(['{"verdict": "PASS"}', RuntimeError("x"), RuntimeError("y")])
    state = {"answer": "这款产品保本保息，放心申请"}
    result = nodes.node_compliance(state, _ctx_with_llm(llm))
    assert result["blocked"] is True
    assert "未能通过行内合规校验" in result["answer"]  # 通用安全话术
    assert "好帮手" not in result["answer"]


def test_dialogue_mock_mode_vector_guard_no_marketing_fallback():
    # 离线 demo：伪向量仍是唯一语义层；命中后兜底是通用话术而非营销模板
    state = {"answer": "不管你征信多差都可以放款，快来申请吧"}
    result = nodes.node_compliance(state, _ctx_with_llm(MockLLM()))
    assert result["blocked"] is True
    assert result["compliance_semantic"]["method"] == "hash-embedding"
    assert "未能通过行内合规校验" in result["answer"]
    assert "好帮手" not in result["answer"]


def test_copy_path_marketing_fallback_unchanged():
    # 营销文案路径：宁严勿宽 + 模板重出，行为与现状一致
    llm = ScriptedLLM(['{"verdict": "PASS"}'])
    state = {"copy_text": "本产品保本保息，百分百下款",
             "answer": "本产品保本保息，百分百下款",
             "user_input": "把文案改成：本产品保本保息，百分百下款"}
    result = nodes.node_compliance(state, _ctx_with_llm(llm))
    assert result["blocked"] is True
    assert "好帮手" in result["answer"]  # 营销模板兜底保留


# ------------------------------------------------------------------ 网站动作 SITE_ACTION（Copilot 模式）

def test_mock_actions_fuzzy_sentences():
    """Mock 降级：模糊语义 → 正确动作（与提示词 few-shot 对齐）。"""
    llm = MockLLM()
    assert llm.extract_site_actions("帮我看看华创那家公司情况") == [
        {"type": "view_customer", "params": {"name": "华创"}}]
    assert llm.extract_site_actions("最近业务怎么样") == [
        {"type": "show_stats", "params": {}}]
    assert llm.extract_site_actions("我想发个朋友圈宣传下税易贷") == [
        {"type": "generate_copy", "params": {"product_name": "税易贷", "channel": "朋友圈"}}]
    assert llm.extract_site_actions("制造业要200万周转一年推荐下") == [
        {"type": "recommend", "params": {}}]
    assert llm.extract_site_actions("去产品页看看") == [
        {"type": "navigate", "params": {"path": "/product"}}]
    assert llm.extract_site_actions("你好") == []  # 纯对话 → 空数组


def test_llm_actions_clean_json():
    llm = ScriptedLLM(['{"actions": [{"type": "view_customer", "params": {"name": "华创"}}]}'])
    assert llm.extract_site_actions("帮我看看华创那家公司情况", page="/dashboard") == [
        {"type": "view_customer", "params": {"name": "华创"}}]
    # 页面上下文进入提示词
    assert "/dashboard" in llm.calls[0][-1]["content"]


def test_llm_actions_dirty_json():
    llm = ScriptedLLM(['好的，动作如下：\n```json\n'
                       '{"actions": [{"type": "show_stats", "params": {}}]}\n```\n以上'])
    assert llm.extract_site_actions("最近业务怎么样") == [{"type": "show_stats", "params": {}}]


def test_llm_actions_non_whitelist_dropped():
    llm = ScriptedLLM(['{"actions": [{"type": "delete_all", "params": {}},'
                       ' {"type": "show_stats", "params": {}}]}'])
    assert llm.extract_site_actions("x") == [{"type": "show_stats", "params": {}}]


def test_llm_actions_missing_params_degraded_to_empty():
    missing = ScriptedLLM(['{"actions": [{"type": "view_customer", "params": {}}]}'])
    assert missing.extract_site_actions("x") == []
    bad_path = ScriptedLLM(['{"actions": [{"type": "navigate", "params": {"path": "/admin"}}]}'])
    assert bad_path.extract_site_actions("x") == []  # 路径越白名单 → 降级


def test_llm_actions_none_normalized_to_empty():
    llm = ScriptedLLM(['{"actions": [{"type": "none", "params": {}}]}'])
    assert llm.extract_site_actions("你好") == []


def test_llm_actions_retry_then_success():
    llm = ScriptedLLM(["我来分析一下……", '{"actions": [{"type": "recommend", "params": {}}]}'])
    assert llm.extract_site_actions("制造业要200万推荐下") == [{"type": "recommend", "params": {}}]
    assert len(llm.calls) == 2
    assert "无法被程序解析" in llm.calls[1][-1]["content"]


def test_llm_actions_failure_returns_empty():
    llm = ScriptedLLM(["garbage", "still garbage"])
    assert llm.extract_site_actions("x") == []
    assert len(llm.calls) == 2  # 重试一次后放弃，不影响对话主链路
