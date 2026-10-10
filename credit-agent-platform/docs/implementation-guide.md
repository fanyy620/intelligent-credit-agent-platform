# 重点实现路径说明（implementation guide）

本文是 `credit-agent-platform` 的核心交付文档，按模块讲清五件事：
**设计动机 → 数据流 → 关键代码位置 → 调优要点 → 踩坑记录**。

代码定位约定：`文件路径 › 函数/类名`。行号会随迭代漂移，以符号名为准。

---

## 1. 总体架构与主流程数据流

### 1.1 设计动机

信贷助手不是“一个 Prompt 走天下”的聊天机器人：它要同时满足 **业务正确性**
（推荐的产品必须过准入）、**合规底线**（文案不能有一句违规话术）、
**个性化**（客户第二次来要“记得”他）。因此主流程被设计为一条有向图
流水线，每个节点单一职责、可独立测试、可独立替换。

### 1.2 数据流

```
用户输入
  → memory_read     读短期窗口 + 长期事实召回 + 槽位继承
  → route_intent    LoRA 模型 / Prompt 基线，输出 10 类意图之一
  → 意图分支        consult / rate_query / recommend / copywriting / chitchat / human
  → compliance      双重风控（正则 + 语义），命中则整体替换答复
  → memory_write    短期追加 + 长期事实 upsert（推荐结果也记为事实）
```

### 1.3 关键代码

- 状态定义：`src/agent/state.py › AgentState`（TypedDict，langgraph 原生兼容，普通 dict 也能用）
- 节点实现：`src/agent/nodes.py`（全部为 `(state, ctx) -> partial_state` 纯函数）
- 图编排：`src/agent/graph.py › run_turn / _build_langgraph / _sequential_run`
- 依赖装配：`src/agent/graph.py › build_context`

### 1.4 双执行引擎（重点）

`graph.py` 同时实现了两条执行路径：

1. **LangGraph StateGraph**（`langgraph` 已安装时）：条件边按意图分发；
2. **顺序流水线**（零依赖降级）：`_sequential_run` 按固定拓扑调同一批节点函数。

两条路径共享 `nodes.py`，行为完全一致 —— 这就是“不装 langgraph 也能跑
demo 和测试”的原因。**凡是编排层的逻辑（分支、汇流）只写在 graph.py，
节点内部永不 import langgraph**，这是保持可降级性的关键纪律。

### 1.5 调优要点

- 新增意图 = 在 `src/intent/labels.py` 加标签 + 在 `graph.py › _DISPATCH` 加映射 +
  在 `data/generate_intent_data.py › TEMPLATES` 加模板，三处一改全链路生效；
- 节点要读历史时优先用 `memory_context.inherited_slots`（已做好跨轮槽位合并），
  不要直接翻原始会话文本。

---

## 2. 意图路由：Prompt 基线 vs LoRA 微调

### 2.1 设计动机

意图识别是全链路的“总开关”：路由错了，后面推荐、文案、合规全部白做。
Prompt 基线（把 10 个标签写进系统提示词让通用 LLM 选）上线后教学复盘发现
三个硬伤：

1. **不稳**：口语化复合句（“我月入一万五想借20万装修帮我看看”）在
   `产品咨询/授信推荐` 之间摇摆，实测约 70% 准确率；
2. **贵**：每次请求附带整段标签 Prompt，Token 成本随标签数线性涨；
3. **格式不可控**：模型偶尔输出解释性文字，解析兜底逻辑越写越厚。

1000 条业务对话数据 + LoRA 微调小模型（Qwen2.5-1.5B）把准确率提到 **85%+**，
且推理成本几乎为零（本地小模型，16 个 token 出标签）。

### 2.2 数据流

```
data/generate_intent_data.py ──1000条──> training/llama_factory/data/intent_sft.json
        │                                        │
        └── data/intent_samples.jsonl（质检用）    ▼
                                   LLaMA-Factory LoRA SFT（intent_lora_sft.yaml）
                                                ▼
                                   合并导出 models/intent-lora-merged
                                                ▼
                     src/intent/lora_router.py › LoraIntentRouter.route
                     （不可用 → PromptIntentRouter 透明回退）
```

### 2.3 关键代码

- 标签体系（单一事实来源）：`src/intent/labels.py › ALL_INTENTS`
- 基线路由：`src/intent/prompt_router.py › PromptIntentRouter`
- LoRA 路由：`src/intent/lora_router.py › LoraIntentRouter.route / _try_load / _infer`
- 训练数据生成：`data/generate_intent_data.py › generate / to_alpaca`
- 训练配置：`training/llama_factory/intent_lora_sft.yaml`

### 2.4 调优要点（LoRA 超参）

| 超参 | 取值 | 经验依据 |
|------|------|----------|
| `lora_rank / lora_alpha` | 16 / 32 | 1000 条小数据 rank 8–16 足够；alpha=2×rank 稳定缩放 |
| `learning_rate` | 1e-4 | 小模型+小数据：2e-4 验证集震荡，5e-5 收敛过慢 |
| `num_train_epochs` | 3 | 第 3–4 轮后验证 loss 回升，早停于 3 |
| `cutoff_len` | 512 | 样本最长约 60 字，512 省显存且不影响效果 |
| `val_size` | 0.1 | 留 100 条监控过拟合拐点 |
| `lora_target` | all | 意图分类依赖语义整体迁移，全线性层比只挂 q/v 稳 |

数据侧：10 类意图严格均衡（各 100 条），口语化前缀/后缀随机拼接防模板记忆；
`seed` 固定保证评测可复现（`generate(n, seed)` 两次输出逐字节一致，有单测守护）。

### 2.5 踩坑记录

- **Prompt 路由的“隐形失败”**：模型输出有时带句号、有时换行，解析必须
  只取首个 `A-Z_` token 并兜底 CHITCHAT（`prompt_router.py` 与
  `lora_router.py › _infer` 同款正则兜底）；
- **降级不是 try/except 一把梭**：LoRA 不可用有三种形态（模型目录不存在 /
  缺 transformers / 加载中OOM），`route()` 对每种都回退并在
  `RouteResult.backend="prompt_fallback"` + `detail` 中留痕，可观测性里能看到
  每一次降级发生的原因；
- **惰性加载**：模型在首次 `route()` 时才加载，避免拖慢服务启动与测试。

### 2.6 Prompt 工程与 LoRA 路由分工

五层 LLM 交互（意图/槽位/推荐理由/文案模板/语义审核）统一收敛到
`src/llm/prompts.py`（提示词单一事实来源）+ `src/llm/client.py`
（调用/解析/重试/降级管线），设计全貌见 `docs/prompt-design.md`。
意图层是其中唯一"双轨制"的层，分工如下：

| 维度 | LoRA 路由（首选） | Prompt 路由（兜底/冷启动） |
|------|-------------------|----------------------------|
| 成本 | 本地小模型，16 token 出标签，≈0 | 每次附带整段标签表 + few-shot，约 1k token/次 |
| 准确率 | 85%+（1000 条业务数据微调） | 通用模型约 70%，靠 JSON 契约 + few-shot 补强 |
| 冷启动 | 需训练与导出，环境重 | 零训练，配 Key 即用 |
| 稳定性 | 输出格式固定（训练分布内） | 需宽松解析 + 修复重试 + 关键词降级三段兜底 |

分工原则：**LoRA 解决高频主链路的成本与稳定性，Prompt 解决冷启动与兜底**
——两者共用 `src/intent/labels.py` 同一标签体系（单一事实来源），
`LoraIntentRouter.route()` 任何失败都透明回退 `PromptIntentRouter`，
而 Prompt 路由再失败时降级 MockLLM 关键词（`client.py › classify_intent`），
形成"LoRA → Prompt → 关键词"三级防线，每一级都在 `RouteResult.detail`
留痕可审计。

其余四层（槽位/回复/文案/审核）调用频次低一个数量级且需要通用语义
理解力（对公口语变体、创意文案、换皮违规话术），不适合小模型微调，
保持通用 LLM 提示词驱动 + 确定性降级即可。

---

## 3. 三层产品推荐架构（核心）

### 3.1 设计动机

直接让 LLM“看着产品列表推荐”有两个死穴：**不可解释**（为什么推这个？）
和 **不可靠**（可能推客户根本不符合准入的产品）。三层架构把问题分解为：

1. **槽位抽取**：把自然语言变成结构化检索条件；
2. **召回**：规则保证“合规准入 100% 正确”，语义召回解决“相关性排序”；
3. **重排**：多维业务评分给出可解释、可调参的最终顺序，LLM 只做有限增强。

### 3.2 数据流（以“我月收入1万5，想借20万装修房子，3年内还清，征信良好”为例）

```
槽位抽取（slots.py）      amount=20万 term=36月 purpose=装修 income=15000 credit=650
        │
第一层 规则硬过滤          8 个产品 → 通过 2 个（信享贷、安居房抵贷）
（recall.py›rule_filter）  其余 6 个各自带拒绝原因（额度超限/用途不符/期限不符）
        │
第二层 RAG语义召回         对通过项打语义分（PGVector ≤> 或伪 embedding 余弦）
（recall.py›rag_recall）
        │
第三层 业务评分重排        final = 0.75×business + 0.25×semantic
（rerank.py›rerank）       business = 0.3×额度 + 0.3×利率 + 0.2×期限 + 0.2×速度
        │
        └→ Top1 信享贷（综合分 0.608）+ 四维分数明细 + LLM 推荐理由
```

### 3.3 关键代码

- 槽位 schema 与抽取：`src/recommend/slots.py › SlotSet / extract_slots_rules / extract_slots`
- 产品目录与准入字段：`configs/products.yaml` + `src/recommend/catalog.py › Product`
- 第一层：`src/recommend/recall.py › rule_filter / _check`
- 第二层：`src/recommend/recall.py › rag_recall / recall_two_stage`
- 第三层：`src/recommend/rerank.py › business_score / rerank / RankWeights`
- 编排接入：`src/agent/nodes.py › node_recommend`

### 3.4 评分公式与权重调优

```
amount_score : max_amount/请求额 ∈ [1,3] → 0.7~1.0；>3 倍后线性衰减（最低 0.2）
rate_score   : 产品最低年化在全库区间 min-max 归一，越小越高分
term_score   : min(1, 产品最长期限 / 请求期限×1.5)，奖励期限弹性
speed_score  : 审批时效全库归一，越快越高分
business     = 0.30×amount + 0.30×rate + 0.20×term + 0.20×speed
final        = 0.75×business + 0.25×semantic_score
```

调参入口：`configs/settings.py › weight_*`（业务权重必须和为 1，
`RankWeights.validate()` 有单测守护）。调参经验：

- **冲量期**提高 `weight_speed`（审批快转化高）；**利润导向**提高
  `weight_rate` 并反转打分方向（推高利率产品需合规评审）；
- `semantic_weight` 建议 0.2–0.3：再高会让“话术像但资质不合适”的产品翻盘；
- 归一化基准必须取**全库**而非当前候选（`CatalogStats.from_catalog`），
  否则同一产品在不同请求下分数不可比。

### 3.5 踩坑记录（本工程真实修复）

- **“额度富余度”陷阱**：初版 amount_score 奖励“额度上限越高越好”，
  结果 500 万房抵贷在“20 万装修”场景下打败 30 万消费贷 —— 业务上没人会
  为 20 万装修去抵押房产。改为“贴合度”打分（max/req ≤ 3 倍为理想区间），
  并有单测 `test_rerank_score_formula` 锁定 Top1=信享贷；
- **槽位遮蔽**：不先遮蔽“月收入1万5”，金额正则会把它误抽成借款金额
  （`slots.py › extract_slots_rules` 中 income 先行抽取 + 掩码，有单测守护）；
- **LLM 重排的边界**：LLM 只允许在 Top3 内微调顺序并给理由，**不允许**把
  低分产品顶到首位 —— 评分是业务底线，模型只是体验增强。

---

## 4. 双重风控文案体系

### 4.1 两道闸的分工

| 闸 | 手段 | 能拦什么 | 拦不住什么 |
|----|------|----------|------------|
| 正则（regex_guard） | 违规词库匹配 | 写明的坏话术：“保本保息”“百分百下款”“无视黑白户” | 换皮表达：“不管你资质如何都能批” |
| 语义（semantic_guard） | 与违规样本库向量比对 + 可选 LLM 复核 | 近义换皮、阴阳话术 | 全新话术（需持续补样本库） |

教学复盘：单正则合规通过率约 70%，双闸联合 >90%（语义闸兜住换皮表达）。

### 4.2 关键代码与调优

- 词库：`src/compliance/regex_guard.py › RULES`（8 类规则，每条含
  原因与修改建议 —— 拦截输出必须“说人话”，告诉客户经理怎么改）
- 语义审核：`src/compliance/semantic_guard.py › check_semantic /
  VIOLATION_EXEMPLARS`；伪 embedding 下阈值经验值 **0.55**
  （`DEFAULT_THRESHOLD`，真 embedding 需重新标定，建议按验证集 F1 选阈值）
- 出口把关：`src/agent/nodes.py › node_compliance`（**所有意图分支的答复
  统一过合规节点**，包括闲聊 —— 合规不信赖任何上游）

### 4.3 数值幻觉：模板 + 数据后填充

`src/compliance/template_fill.py` 实现的是一条铁律：
**营销文案中的数字，LLM 一个都不许生成**。

```
LLM 只产出模板：  "【{product_name}】最高可借{max_amount}，年化利率低至{rate_min}起…"
代码校验：         find_free_numbers() 发现模板里出现游离数字 → 整篇拒绝渲染
代码填充：         product_slot_data(product) 从结构化字段取数（唯一事实来源）
强制兜底：         render_copy() 自动追加免责声明（模型无权删改）
```

对照演示（demo 结尾自动打印）：`template_fill.py › hallucination_contrast_demo`
展示同一产品下“LLM 直出文案”（编造 50 万/3.6%/秒批）与“模板填充”的差异。

### 4.4 踩坑记录

- **幻觉不止于“编造”**：模型会把 A 产品的利率安到 B 产品头上 —— 所以校验
  粒度是“模板中不允许出现任何数字”，而不是“数字要和产品一致”；
- **免责声明必须代码追加**：让模型自己写风险提示，十次总有一次会“忘记”；
- **正则占位符别泄露违规词**：`redact()` 初版占位符带规则名（含违规词本身），
  等于二次曝光，已改为通用占位（`test_compliance.py` 有单测守护）。

---

## 5. 分层记忆体系

### 5.1 设计动机

单 Redis 会话记忆的问题：会话一断客户画像全丢；单向量库的问题：当前对话
的即时上下文（“那 20 万呢”这种指代）检索噪声大。分层方案各取所长：

- **短期（Redis）**：会话内最近 N 条消息，TTL 1 小时，滑动窗口 20 条；
- **长期（PGVector）**：结构化事实（月收入/用途/意向额度/职业/征信…），
  同键新值覆盖旧值，按语义召回，跨会话存活。

### 5.2 关键代码

- 短期：`src/memory/redis_memory.py › ShortTermMemory`（`_InMemoryBackend`
  为 Redis 的零依赖替身，TTL 语义一致）
- 长期：`src/memory/pgvector_memory.py › LongTermMemory`（DDL 常量与
  `scripts/init_db.sql` 保持一致；`ON CONFLICT (user_id, fact_key)` 覆盖更新）
- 门面：`src/memory/manager.py › MemoryManager.read_context / write_turn /
  extract_facts`
- 节点接入：`src/agent/nodes.py › node_memory_read / node_memory_write`

### 5.3 写入/读取策略（调优要点）

- **写入时机**：只在推荐类意图（CREDIT_RECOMMEND/LIMIT_QUERY）做事实抽取。
  踩过的坑：咨询轮里“消费贷”会被误存为“借款用途=消费”，污染画像
  （`node_memory_write › extract` 开关）；
- **推荐结果也是事实**：Top1 产品名写入 `最近推荐产品`，下一轮
  “针对这款产品写文案”才能跨轮解析（`_resolve_product` 按
  本轮重排 → 记忆事实 → 名称匹配 → 兜底 的顺序解析）；
- **读取融合**：短期窗口原文 + 长期事实 top_k=5 + 从最近 6 条用户消息
  重抽的“继承槽位”三者打包为 `MemoryContext`；
- **真实环境升级**：`extract_facts` 的规则抽取可换 LLM 抽取（接口已预留），
  建议保留“规则优先、LLM 补缺”的合并顺序 —— 事实记忆必须可审计。

---

## 6. MCP 服务：stdout/stderr 隔离踩坑实录

### 6.1 事故复盘

MCP stdio 传输约定 stdout 是**纯 JSON-RPC 协议通道**。早期版本在工具函数里
`print()` 调试、logging 默认也打到 stdout，客户端把日志行当成 JSON 解析，
直接断连，表现为“工具时灵时不灵”，排查成本极高。

### 6.2 修法（`src/mcp_server/server.py` 顶部注释 + 全文件执行）

1. `logging.basicConfig(stream=sys.stderr)` —— 日志只走 stderr；
2. 全文件唯一 stdout 写点：`_send()` 中的 `sys.stdout.write(json.dumps(...))`；
3. 工具内部异常捕获后以 JSON-RPC error 返回，绝不向 stdout 抛 traceback。

验证：`python -m src.mcp_server.server --selftest` 会在进程内断言每个响应
都是合法 JSON-RPC；也可管道实测：`echo '<json-rpc>' | python -m src.mcp_server.server`，
stdout 每一行都必须能 `json.loads`。

### 6.3 工具清单

- `get_interest_rate(product_name)`：利率区间/期限/最高额度（数据来自
  产品库结构化字段，绝不现场编造）；
- `search_products(query, top_k)`：语义检索（伪 embedding 实现，接口与
  PGVector 版一致，可无缝替换）。

---

## 7. Langfuse 全链路可观测

### 7.1 设计

`src/observability/tracing.py` 提供 `Tracer.span()/event()` 两级 API，
业务节点以 `with tracer.span("intent.route", ...)` 形式零侵入埋点。
每个 span 记录：名称、时延、关键属性（意图标签、召回条数、合规命中数、
后端类型）。配置 `LANGFUSE_*` 后自动升级 `LangfuseTracer` 同步上报；
未配置时 `NoopTracer` 保留内存缓冲，demo 结尾打印离线 trace 摘要
（41 个 span / 5.7 ms 的实测输出见 demo）。

### 7.2 埋点地图

| span | 节点 | 关键属性 |
|------|------|----------|
| `memory.read` | node_memory_read | backend、history_len、facts |
| `intent.route` | node_route_intent | intent、backend |
| `slots.extract` | node_recommend | channel=rules+llm |
| `recall.two_stage` | node_recommend | total、passed |
| `rerank.business` | node_recommend | — |
| `compliance.regex/semantic` | node_compliance | regex_hits、semantic_passed |
| `memory.write` | node_memory_write | new_facts |

生产建议：在 LLM 调用处补 `token_in/token_out`（DeepSeek 响应 usage 字段），
即可在 Langfuse 看板做时延/Token/准确率三维监控。

---

## 8. 优雅降级设计总纲

全工程遵循一条纪律：**第三方依赖一律函数内 import 或 try/except 包裹**，
且每个降级路径都保持接口与分数域一致（如语义分恒为 [0,1]）。降级总表见
README「优雅降级总表」。这让三类人都能用好本工程：没有外部服务的读者
跑通全流程、有服务的读者无缝升级、写测试的人不需要任何 mock 框架。

## 9. 基于中金 Multi-Agent 方法论的优化

> 动机来源：中金《大模型系列(6)：Multi-Agent 如何辩论出基本面 Alpha？》。
> 逐条机制对照（含代码位置）见 docs/cicc-methodology-mapping.md，本节只讲设计决策。

### 9.1 为什么引入

三层推荐给出的 Top1 是"评分最优"，但评分只覆盖额度/利率/期限/速度四个
业务维度——客户没说的风险（偿债能力未验证、征信未披露、现金流真实性）
不在公式里。研报的答案是 Multi-Agent 辩论：让不同视角的 Agent 围绕同一
对象相互质疑。我们把它映射为信贷语境的双视角评审：**风险合规视角 ×
业务增长视角**，插入位置在重排之后、回复生成之前（`node_recommend`）。

### 9.2 设计要点

- **结构化意见才能进机制**：视角输出 JSON
  `{stance, points[], suggested_caveats[], score_adjust}`，
  `_sanitize_debate` 做第二道闸（stance 越枚举归一"谨慎支持"、score_adjust
  钳制 ±0.2）——自由文本无法被裁决消费，这是"机制设计 > 模型能力"的直接体现；
- **硬伤检测是确定性规则，不是模型判断**：`detect_hard_issues`（偿付比 >
  年收入 3 倍）+ 风险视角 stance=反对 并列进入裁决，触发"风险提示分区 +
  Top2 再评估说明"。对应研报 RES 因子案例中"提质与去同质"：我们的
  "Top2 再评估"就是质疑驱动的结论修正；
- **PIT 数据约束的信贷等价物**：研报用 PIT 防未来信息泄露，我们用
  `PIT_CLAUSE`（注入 SLOT/REPLY/DEBATE 三层 prompt）防"脑补"客户财务数据——
  LIVE 实测双视角均遵守（意见只写"待核实事项"，未编造任何数字）；
- **经验库 = 因子库经验记忆**：final_score≥0.5 且未拦截的推荐沉淀为经验
  条目，下一轮按槽位相似度检索注入辩论上下文；`exclude_session` 防自引用
  回声；相似度公式（用途0.4+身份0.3+金额0.2+期限0.1）确定性可测试；
- **降级纪律不变**：辩论失败/超时返回 None 不阻塞主回复；MockLLM 的
  模板化视角意见与硬伤规则同源口径（离线模式裁决自洽）；
  `DEBATE_ENABLED=0` 一键关闭（LIVE 实测开辩论端到端 178.8s，其中两次
  视角调用约占 60-70s，延迟敏感场景可关）。

### 9.3 关键代码

- `src/debate/engine.py`：run_debate（双视角调用→裁决→风险提示/Top2 再评估）、
  detect_hard_issues（确定性硬伤规则）；
- `src/llm/prompts.py`：第 8 层 debate_messages（DEBATE_PERSPECTIVES 视角定义 +
  PIT_CLAUSE + 不得编造财务数据）；
- `src/llm/client.py`：debate_perspective 三实现（Base/Mock/OpenAICompat）+
  `_sanitize_debate`；
- `src/memory/experience.py`：ExperienceStore（maybe_save 阈值沉淀 /
  search_similar 相似检索）；
- `src/agent/nodes.py`：node_recommend 集成（experience.recall →
  debate.dual_perspective → 回复风险提示分区）、node_memory_write 沉淀；
- `tests/test_debate.py`：16 个用例全离线。

### 9.4 LIVE 实测摘录（2026-07-25，kimi-for-coding-highspeed）

200 万制造业案例：风险视角 stance=谨慎支持、score_adjust=-0.15，指出
"200万大额授信，偿债能力无数据验证 / 税易贷核心依赖纳税数据，客户未提供"；
增长视角 stance=谨慎支持、score_adjust=-0.05；回复正文呈现
"风险提示：应补充近两年纳税记录与财务报表 / 应提供企业及个人征信报告 /
应明确资金具体用途与回款路径"。无收入信息 → 无规则硬伤 → 未触发
Top2 再评估（行为与测试断言一致）。

## 10. 测试策略

`tests/` 95 个用例全部零外部依赖：

- `test_recommend.py`：槽位抽取（含“1万5”遮蔽回归）、规则过滤的通过/拒绝原因、
  语义分有界且有序、评分公式自洽（final = 0.75×business + 0.25×semantic）、
  权重校验、Top1 业务直觉锁定；
- `test_compliance.py`：8 类违规话术逐条参数化拦截、干净文本放行、
  语义换皮命中、模板填充（槽位全替换/游离数字拒绝/缺槽报错/免责声明强制）、
  对照示例本身必须违规（防示例失真）；
- `test_intent_data.py`：≥200 条、schema 合法、≥8 类意图、无重复、
  生成器确定性、alpaca 格式与 dataset_info 一致性；
- `test_debate.py`：PIT 条款存在性、辩论 JSON 解析闸、Mock 视角意见、
  高杠杆反对 stance、硬伤触发 Top2 再评估、失败降级、经验库读写与跨轮流动、
  DEBATE_ENABLED 开关（见 §9）。

## 11. 已知限制与后续路线

1. 伪 embedding 只有关键词重合度，无语义泛化 —— 接 bge 后需重新标定
   语义阈值与 `semantic_weight`；
2. 征信分由“良好/一般/有逾期”映射估算（650/580/520），真实场景应接征信接口；
3. 申请流程/还款方式/材料咨询三个意图当前落到产品总览节点（教学简化），
   可补专属知识库节点；
4. LLM 重排当前只生成理由不换序，真实环境可放开 Top3 内 ±1 名交换；
5. 产品库 8 个为教学配置，准入规则字段可平滑扩展（如抵押物类型、行业禁入）。
