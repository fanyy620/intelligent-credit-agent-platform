# Prompt 工程设计说明（prompt-design）

本工程的全部 LLM 交互已重构为**真实提示词驱动**：五层提示词集中于
`src/llm/prompts.py`（单一事实来源），调用与解析管线集中于
`src/llm/client.py`。本文档记录每层 prompt 的设计目标、结构、few-shot
理由、输出约束与修复策略、防数值幻觉机制，以及接入真实模型
（Kimi for Coding / DeepSeek）后的实测调优记录。

## 1. 设计目标

| 目标 | 机制 |
|------|------|
| 对话不再依赖关键词死逻辑 | 意图/槽位/推荐理由/文案模板/语义审核五层全部走 LLM 提示词 |
| 无 Key 时行为与重构前完全一致 | 每层保留确定性降级（MockLLM 关键词/规则/内置模板），`get_llm()` 探测链兜底 |
| 数值零幻觉 | LLM 永远不产出业务数值——提示词层明令禁止 + 代码层 `find_free_numbers` 拦截 |
| 输出可机读 | JSON/定界标签输出契约 + 宽松解析 + 修复重试一次 + 确定性降级 |
| 测试零网络依赖 | conftest 默认强制 `LLM_PROVIDER=mock`；真实联调 `LIVE=1` 显式开启 |

人设统一为**南洋商业银行（中国）对公信贷顾问**（`prompts.PERSONA`）：
专业稳健、不夸大、不承诺审批结果、不编造数字，五层共用保证口吻一致。

## 2. 八层提示词总览

| 层 | 入口 | 输出契约 | 失败降级 |
|----|------|----------|----------|
| 意图 INTENT | `intent_messages(text)` | `{"intent": code, "reason": ...}`（兼容裸标签） | Mock 关键词分类 |
| 槽位 SLOT | `slot_messages(text, schema)` | JSON 对象，schema 白名单 + 类型强制 | 返回 {}（规则通道已先行） |
| 回复 REPLY | `reply_messages(product, slots)` | 一句话 ≤40 字，不得含产品数值 | Mock 模板化解释 |
| 文案模板 COPY | `copy_messages(product, tone)` | 无数字模板，仅白名单槽位 | 内置安全模板 `GOOD_LLM_TEMPLATE` |
| 语义审核 COMPLIANCE | `compliance_messages(text)` | `{"verdict": PASS/BLOCK, ...}`（兼容裸词） | 正则 `is_compliant` 结论 |
| 合规重写 REWRITE | `rewrite_messages(text, issues)` | 合规版回复全文（数值原样保留） | 通用安全话术（非营销模板） |
| 网站动作 SITE_ACTION | `site_action_messages(text, page)` | `{"actions": [{"type", "params"}]}`（白名单 7 类 + none） | 返回 []（绝不影响主链路） |
| 双视角辩论 DEBATE | `debate_messages(perspective, product, slots, facts, exp)` | `{"stance", "points", "suggested_caveats", "score_adjust"}` | Mock 规则模板意见（与硬伤规则同源口径） |

（REWRITE 为对话回复专用兜底层，见 §7；DEBATE 为推荐链路专用评审层，见 §3.7。）

## 2.1 PIT 时点约束（中金方法论映射）

中金研报用 PIT（Point-in-Time）限定数据可得时点、防未来信息泄露；
本系统在信贷语境下的等价物是 `PIT_CLAUSE`（prompts.py 顶部常量），
注入 SLOT / REPLY / DEBATE 三层提示词：**仅使用用户在对话中已提供的
信息与产品库静态数据，不得假设或推断用户未提供的财务数据，不得使用
对话之外的任何外部信息**——防的是模型"脑补"客户财报（收入、负债、
征信记录）。三层选择是有讲究的：槽位层防"抽取出用户没说的信息"，
回复层防"推荐理由引用虚构条件"，辩论层防"视角意见编造财报"。
LIVE 实测双视角意见全部以"待核实事项"形式呈现未知信息，零编造。

few-shot 统一走真实的 user/assistant 轮次（`_msgs()`），而非塞进 system
文本——对 chat 模型的格式锚定效果更好。

## 3. 各层设计要点与 few-shot 理由

### 3.1 意图 INTENT

- **为什么选 JSON 而非裸标签**：让模型顺带输出 ≤20 字判别理由，进 trace
  日志可审计（每一次路由都能回答"为什么这么判"）；解析端同时兼容裸标签，
  弱模型/异常输出不死。
- **few-shot 锚定三个易混点**（正是 Prompt 基线约 70% 准确率的病灶）：
  ① 只问"能贷多少"是 `LIMIT_QUERY` 而非 `CREDIT_RECOMMEND`（未给用途/条件）；
  ② 对公复合句（制造业+200万+流动资金+期限）是 `CREDIT_RECOMMEND`；
  ③ "写文案"即使带产品名也是 `COPYWRITING` 而非 `PRODUCT_CONSULT`。

### 3.2 槽位 SLOT

- 取值词表与规则通道（`src/recommend/slots.py`）严格对齐（金额→元、
  期限→月、purpose/occupation/credit_status 枚举），保证双通道语义一致、
  可互相补缺。
- few-shot 显式教会规则通道覆盖不了的**对公口语变体**：
  "流动资金贷款" → `purpose=经营`、`"制造业企业"` → `occupation=企业主`。
  实测中该句槽位 `{amount:2000000, term_months:12, purpose:经营,
  occupation:企业主}` 的 occupation 正是 LLM 补缺的（规则词典无"制造业"）。
- 第二道闸在代码侧：`_sanitize_slots()` 做 schema 白名单过滤 + 类型强制
  （`"2000000"`→float 可救；`"200万"` 带单位文本整条丢弃），
  绝不把脏类型放进 SlotSet（脏类型会在推荐评分的算术里炸掉链路）。

### 3.3 回复 REPLY（推荐理由）

- 五层中唯一允许自由文本的层，但**只允许"解释"，不允许"给数"**：
  产品侧数值（额度/利率/期限/时效）由节点代码从结构化目录拼出，
  提示词明令"不得出现任何产品数值"——从提示词上切断报价幻觉路径。
- 限一句话 40 字：推荐卡片可读，且越短越难编造。
- 实测输出（kimi-for-coding）："您为企业主且用于经营，税易贷基于纳税记录
  提供融资支持。"——引用了产品纳税记录特性且零数值，纪律遵守良好。

### 3.4 文案模板 COPY（防数值幻觉核心层）

- 三重纪律：**提示词禁令**（严禁任何阿拉伯数字、仅白名单槽位、禁绝对化
  用语）→ **代码拦截**（`find_free_numbers` 扫描到游离数字整篇拒渲染，
  换内置安全模板）→ **强制免责声明**（`render_copy` 自动追加，
  模型无权删改）。
- few-shot 给出"正确模板长什么样"，比单纯文字禁令更能稳定输出格式。
- 实测输出："【{product_name}】{category}专属，诚信经营，以税易贷。……
  额度高至{max_amount}，利率低至{rate_min}……"——零数字、槽位规范、
  巧妙化用产品名。

### 3.5 语义审核 COMPLIANCE

- 定位为正则硬拦截之后的**语义第二意见**：专抓换皮表达（"保证都能批下来"
  不含任何正则关键词但语义违规），判定口径宁严勿宽。
- few-shot 一正一反：如实报价且附审批提示 → PASS；无脏字但承诺必过 → BLOCK。
- 实测中该层展现了超出正则的价值：把"经营贷**首选**"判为违规
  （绝对化用语，广告法灰色地带）——正则词库未覆盖。治理方式不是放宽审核，
  而是**源头治理**：copy prompt 增加绝对化用语禁令，compliance prompt 把
  极限词列入违规情形使判定可解释（见 §6 踩坑记录）。

### 3.6 网站动作 SITE_ACTION（Copilot 模式）

- 定位为**模糊语义 → 结构化页面动作**的翻译层，是全站悬浮窗（Copilot）
  的大脑：用户一句"帮我看看华创那家公司"，既要正常对话回复，又要让前端
  跳到企业客户页并打开华创的详情。
- **与 INTENT 层的分工**：INTENT 判"对话意图"驱动回复管线（推荐/文案/咨询），
  本层判"操作意图"驱动前端页面动作。两者并存不互斥——一次 `/v1/chat`
  响应中 `reply`（对话产物）与 `actions`（页面动作）并列返回，前端先执行
  动作再展示回复。仅在请求带 `context.page` 时触发，不带则 `actions=[]`，
  对既有管线零影响。
- **白名单双闸**：提示词约束 7 类动作（navigate / search_customer /
  view_customer / open_product / generate_copy / show_stats / recommend + none），
  `client.py › _sanitize_site_actions` 再做代码级白名单——非白名单动作丢弃、
  必填参数缺失或 navigate 路径越白名单则降级 none、none 归一为 []、最多 2 个
  动作。防的是"幻觉动作"：模型编造一个不存在的动作类型时，前端执行器永远
  不会收到它（前端执行器自身还有第三道白名单校验）。
- **称谓抽取纪律**：企业名/产品名只抽取用户原话中的关键称谓（"华创"），
  不臆造补全为"华创精密制造有限公司"——Agent 没有客户库访问权，模糊匹配
  到完整实体是前端执行器的职责（它有真实数据，用 customerPage 模糊查询
  取首个命中）。few-shot 刻意全部使用模糊语义：口语称谓（"华创那家公司"）、
  泛化问法（"最近业务怎么样"→ show_stats）、场景化表达（"发个朋友圈宣传
  税易贷"→ generate_copy）。
- **降级**：LLM 调用失败/解析失败 → 返回 []，主链路 reply 不受任何影响；
  MockLLM 用 7 条优先级关键词规则模拟（文案 > 推荐 > 看板 > 详情 > 筛选 >
  产品 > 导航），企业称谓用正则 `_COMPANY_MENTION_RE` 非贪婪抽取并剥离
  "帮我看看"类动词前缀。

### 3.7 双视角辩论 DEBATE（中金 Multi-Agent 方法论映射）

- 定位为**推荐结论的结构化评审层**：重排给出"评分最优"的 Top1 后，
  风险合规视角（偿债/征信/现金流/抵押）与业务增长视角（经营改善/
  行业前景/额度适配）各自出具意见——对应中金研报"质量/价值 × 成长/动量"
  的双 Agent 设计，金融推荐语境下的"提质 + 去同质"。
- **输出必须结构化**：`{stance, points[], suggested_caveats[], score_adjust}`
  ——只有结构化意见才能被裁决逻辑消费（stance=反对 触发 Top2 再评估），
  自由文本评审无法进入机制；`_sanitize_debate` 做第二道闸（stance 越枚举
  归一"谨慎支持"、score_adjust 钳制 ±0.2、要点限量限长防长篇编造）。
- **PIT + 不得编造财务数据**：视角只能基于对话已提供信息与产品库静态
  数据，未知信息以"待核实事项"写入 caveats（LIVE 实测：风险视角对
  200 万推荐写"偿债能力无数据验证/纳税数据未提供"，而非编造数字）。
- **经验库注入但防锚定**：相似历史推荐（"相似资质客户曾推荐X，评分Y"）
  注入上下文提升收敛性，提示词明确"仅供参考，不影响本次独立判断"。
- **降级**：LLM 失败 → MockLLM 规则模板意见（与 `detect_hard_issues`
  同源口径：离线模式下"模型意见"与"规则硬伤"天然自洽，不会矛盾裁决）；
  辩论层整体失败返回 None 不阻塞主回复，`DEBATE_ENABLED=0` 可一键关闭。

## 4. 输出约束与修复策略（`client.py › _ask`）

```
原始输出 → _strip_fence（剥 markdown 围栏）
        → _loose_json（取首个 { 到末个 } 再 json.loads）
        → 各层 parse（白名单/类型/枚举校验）
失败时两类重试（共一次）：
  ① 空响应（reasoning 模型 token 预算耗尽于思考）→ 翻倍 max_tokens（≤4096）重试
  ② 解析失败 → 坏输出 + REPAIR_HINT 追加为新的一轮，让模型在上下文中纠错
仍失败 → 确定性降级（§2 表）；网络/HTTP 故障不重试，立即降级
```

设计理由：reasoning 模型（kimi-for-coding）的 `completion_tokens` 包含
思考 token，短预算调用（如 max_tokens=128）会把预算耗尽于思考、
`content` 为空、`finish_reason=length`。空响应与格式错误是两种病灶，
重试策略必须分开（加预算 vs 给纠错指令），混用则两边都治不好。

## 5. Provider 探测链与配置

`get_llm()`（`src/llm/client.py`）：

```
LLM_PROVIDER=mock/kimi/deepseek  →  显式指定
LLM_PROVIDER=auto（默认）        →  DEEPSEEK_API_KEY
                                 →  KIMI_API_KEY / MOONSHOT_API_KEY
                                 →  MockLLM（零 Key 演示/测试）
```

| 环境变量 | 默认 | 说明 |
|----------|------|------|
| `KIMI_API_KEY` / `MOONSHOT_API_KEY` | 空 | 二者任一即可 |
| `KIMI_BASE_URL` | `https://api.kimi.com/coding/v1` | 网关地址可省略版本段，客户端自动补 `/v1` |
| `KIMI_MODEL` | `kimi-for-coding-highspeed` | 延迟最低档；可换 `kimi-for-coding`（更稳）或公共端点模型 |
| `LLM_TIMEOUT` | 45 | 单次调用超时（秒） |
| `LLM_TEMPERATURE` | 1.0 | Kimi for Coding 端点**仅允许 1**；公共端点可调低 |
| `LLM_MAX_TOKENS` | 2048 | reasoning 模型需给足思考预算 |

`/health` 暴露真实后端：`llm_backend`（mock/kimi/deepseek）+ `llm_model`。

## 6. 实测调优记录（真实踩坑）

1. **端点差异**：同一 key 在 `api.moonshot.cn` 返回 401（key 属于
   Kimi for Coding 体系）；`api.kimi.com/coding/v1` 与网关
   `agent-gw.kimi.com/coding/v1` 可用，可用模型 `kimi-for-coding /
   kimi-for-coding-highspeed / k3`。
2. **temperature 锁死**：coding 端点仅允许 `temperature=1`，否则 HTTP 400
   ——故 `LLM_TEMPERATURE` 默认 1.0，意图分类的稳定性靠 JSON 契约 +
   few-shot 保证，而非低温。
3. **reasoning 预算**：五层首版预算（explain/review 768）在实测中约半数
   调用空响应降级；重试翻倍预算后五层全部真实直出（推荐轮 127s：
   意图/槽位/两条推荐理由全 LLM；文案轮 104s：定制模板 + 复核 PASS）。
4. **"首选"事件**：合规复核将 LLM 生成的"经营贷首选"判为违规（绝对化
   用语）——语义审核抓到了正则盲区。治理为源头禁令（copy prompt）+
   判定可解释（compliance prompt 列入极限词），复核口径保持宁严勿宽。
5. **网关 base_url 省略版本段**：部署环境 `KIMI_BASE_URL` 为
   `https://agent-gw.kimi.com/coding/`（无 `/v1`），客户端初始化时
   规范化补全，避免 404。
6. **highspeed 降延迟**：默认模型从 `kimi-for-coding` 切到
   `kimi-for-coding-highspeed`（settings/env 可配）。实测单次调用
   15-30s → 8-12s，推荐轮端到端 91s → 75s（约 -18%）；reasoning token
   与网关负载仍是总耗时的主要构成，面试演示建议提前预热。

## 7. 对话回复与营销文案的合规策略差异（“Top1 误拦事件”实录）

### 事件

穿透实测（vite → mock 8080 → agent 8000 → 真实 Kimi）发现：正常顾问式
推荐回复被合规层拦截（HTTP 200，119.6s，回复变成"[合规拦截]…已为您
改用合规模板重新生成：【安居房抵贷】您的房抵贷好帮手…"）。

### 根因（分层定位，4/4 确定性复现）

| 层 | 结论 |
|----|------|
| 正则硬拦截 | 无命中（"最快X小时审批"恰是词库官方建议表述） |
| 伪向量相似度 | 无命中 |
| LLM 复核 | **4/4 判 BLOCK，理由一致：“使用 Top1 等绝对化排名用语”** |

直接诱因：为治理"首选"绝对化用语，compliance prompt 的违规情形新增了
极限词条款——模型随即把推荐回复中的 **Top1/Top2 排序标签**一致判为
"第一"类绝对化用语。两个放大器：① 复核 prompt 以"审核营销文案"为框架，
与对话回复场景错配；② 命中后的兜底动作不分内容类型，一律替换成营销
模板（答非所问）。

### 修复（策略按内容类型分路）

| | 营销文案（copy_text 存在） | 对话回复 |
|---|---|---|
| 正则硬拦截 | 照常 | 照常 |
| 伪向量相似度 | 启用（宁严勿宽） | **仅离线 demo 启用**（锚点是违规营销话术，对顾问对话误伤面大） |
| LLM 复核 | 启用，宁严勿宽 | 启用，**复核失败默认放行 + tracer 留痕**（宁缺勿滥，对话不是广告投放） |
| 命中后动作 | 内置合规模板围绕原产品重出 | **LLM 按合规约束重写原回复**（数值原样保留）→ 失败用通用安全话术，**绝不用营销模板** |

配套提示词修正：compliance prompt 增加边界条款（"Top1/Top2 等中性序号、
顾问对话中基于产品事实的客观介绍不属于绝对化用语"），并加入"推荐列表
→ PASS"的 few-shot 锚点；新增第六层 prompt `rewrite_messages`（合规重写：
保留业务信息、数值原样保留、禁输出元信息）。

代码位置：`agent/nodes.py › node_compliance`（分路）、
`compliance/semantic_guard.py › check_semantic(use_vector=)`、
`llm/client.py › rewrite_compliant`（Mock 兜底返回通用话术
`SAFE_DIALOGUE_FALLBACK`）。

### 验证

- 离线：7 个新单测（正常回复不误拦 / 复核失败放行 / regex 命中重写 /
  LLM 命中重写 / 重写失败通用话术 / mock 模式伪向量仍生效且不拦成模板 /
  文案路径行为不变）；
- 真实：同一条 ToB 消息直连 8000（74.5s）与穿透 8080（106.8s）各跑一次，
  两腿均返回顾问式推荐回复（`blocked=false`，含真实 LLM 推荐理由），
  推荐字段 `recommendations[0].product.name / scores.final_score`
  经桥接原样透传（snake_case，外层按 camelCase 解析为 None 属解析路径问题）。

## 8. 与 LoRA 路由的分工

见 `docs/implementation-guide.md` §2.6：意图层是"LoRA 优先、Prompt 兜底"
的双轨——LoRA 解决成本与稳定性，Prompt（本层）解决冷启动与兜底；
其余四层（槽位/回复/文案/审核）不承担高频路由职责，保持通用 LLM
提示词驱动即可。
