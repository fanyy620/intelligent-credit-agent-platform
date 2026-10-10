# 中金《Multi-Agent 如何辩论出基本面 Alpha》方法论映射表

> 来源：中金公司研究部《大模型系列(6)：Multi-Agent 如何辩论出基本面 Alpha？》。
> 本文档给出研报机制 → 本系统（credit-agent-platform）实现的逐条对照，
> 每条注明代码位置。核心立场与研报一致：**机制设计 > 模型能力**——
> 用批判、修正、验证、评估的机制收敛 LLM 的创造力，而非依赖更大的模型。

## 对照总表

| 中金机制 | 本系统实现 | 代码位置 |
|----------|-----------|----------|
| **Multi-Agent 双视角辩论**：质量/价值 Agent × 成长/动量 Agent 围绕同一对象相互质疑、迭代改写 | 「风险合规视角 × 业务增长视角」围绕 Top1 推荐各自出具结构化意见（stance/points/caveats/score_adjust），裁决层消费意见产出风险提示与 Top2 再评估——金融推荐语境下"提质"（暴露偿付风险）与"去同质"（双视角分工避免单一叙事）的等价物 | `src/debate/engine.py › run_debate`；视角定义 `src/llm/prompts.py › DEBATE_PERSPECTIVES`（第 8 层 DEBATE_PROMPT） |
| **Correction Agent**：校验失败时按错误信息自动修正，减少人工调试 | 两道：① 输出层——`_sanitize_debate` 对非法意见归一/钳制，结构非法触发 `_ask` 修复重试（把坏输出+REPAIR_HINT 回喂模型自纠错）；② 推荐层——`detect_hard_issues` 确定性校验失败时，"修正"动作是风险提示分区 + Top2 再评估说明，而非人工介入 | `src/llm/client.py › _sanitize_debate / _ask`；`src/debate/engine.py › detect_hard_issues` |
| **"自由探索—约束搜索"两阶段 + 经验库记忆**：历史优质结果沉淀经验库，相关性反馈注入下一轮 prompt | 推荐经验库：final_score≥0.5 且未被合规拦截的推荐沉淀为经验条目（槽位摘要+产品+评分）；下一轮推荐按槽位相似度（用途0.4+身份0.3+金额0.2+期限0.1）检索，注入辩论上下文（"相似资质客户曾推荐X，评分Y"）。"自由探索"对应召回与重排的全量评分，"约束搜索"对应规则硬过滤 + 辩论裁决 | `src/memory/experience.py › ExperienceStore`；注入点 `src/agent/nodes.py › node_recommend`（experience.recall span）；沉淀点 `node_memory_write` |
| **PIT（Point-in-Time）数据约束**：prompt 层限定数据可得时点，防未来信息泄露 | 信贷语境等价物：prompt 层限定"信息可得范围"——SLOT / REPLY / DEBATE 三层提示词统一注入 `PIT_CLAUSE`（仅使用对话已提供信息 + 产品库静态数据，不得推断未提供的财务数据，不得使用外部信息），防模型"脑补"客户财报 | `src/llm/prompts.py › PIT_CLAUSE`（slot_messages / reply_messages / debate_messages 引用） |
| **"评估—反馈—再生成"闭环**：量化指标反馈驱动下一轮生成方向 | 重排四维评分（量化指标）→ 辩论视角据此评审并给 score_adjust 反馈 → 裁决：硬伤触发时对 Top2 再评估并在回复中呈现备选方案；合规复核 verdict 作为另一路反馈驱动重写/换版 | `src/debate/engine.py › run_debate`（reevaluated_top2 / top2_note）；`src/agent/nodes.py › node_compliance`（rewrite/换版） |
| **机制设计 > 模型能力** | 全系统铁律的延续：硬伤检测是确定性规则（不依赖模型判断）；辩论失败/超时返回 None 不阻塞主回复；DEBATE_ENABLED 一键关闭；MockLLM 模板化视角意见与规则硬伤同源口径，离线可跑可测 | `src/debate/engine.py`（docstring 与降级路径）；`src/agent/graph.py › build_context`（DEBATE_ENABLED env）；`src/llm/client.py › MockLLM.debate_perspective` |

## 与研报 RES 因子案例的对照

研报中双 Agent 围绕 RES 因子反复质疑、改写直至收敛，产出"提质 + 去同质"
的因子定义。本系统的对应过程：

1. **评审对象**：不是因子，而是"Top1 推荐结论"（产品 + 客户画像 + 四维评分）；
2. **质疑方式**：风险视角专挑偿付/征信/抵押短板（LIVE 实测：对 200 万税易贷
   推荐给出 stance=谨慎支持、score_adjust=-0.15，指出"偿债能力无数据验证、
   纳税数据未提供"）；增长视角专找经营适配与成长合理性；
3. **改写/收敛**：不是改写因子，而是改写"呈现给客户的结论形态"——
   无硬伤时推荐卡 + 风险提示分区；有硬伤时追加 Top2 再评估说明（备选方案）；
4. **经验复用**：高分案例入经验库，下一轮相似画像客户直接获得
   "历史参照系"（收敛性与可复现性提升）。

## 测试与验证

- 离线测试：`tests/test_debate.py`（16 个用例：PIT 条款存在性、JSON 解析闸、
  Mock 视角意见结构、高杠杆反对 stance、硬伤触发 Top2 再评估、失败降级 None、
  经验库阈值/检索/排除本会话、API 端到端 debate 字段、DEBATE_ENABLED 关闭、
  经验跨轮流动）；
- LIVE 验证（2026-07-25，kimi-for-coding-highspeed）：200 万制造业案例
  端到端 178.8s，debate 字段返回双视角真实意见与 3 条风险提示，
  回复正文出现"风险提示："分区，无硬伤未触发 Top2 再评估（符合预期，
  因客户未提供收入信息）。
