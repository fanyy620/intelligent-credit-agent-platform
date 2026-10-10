# LoRA 意图路由模型训练指南

目标：用 1000 条业务对话数据对 Qwen2.5-1.5B-Instruct 做 LoRA SFT，
得到本地意图分类器，替换 Prompt 路由（教学复盘：准确率 70% → 85%+）。

## 1. 数据准备

```bash
# 在 credit-agent-platform 根目录执行（零依赖）
python data/generate_intent_data.py            # 生成 1000 条
# 产物：
#   data/intent_samples.jsonl                        （查看/质检用）
#   training/llama_factory/data/intent_sft.json      （alpaca 格式，训练用）
```

把本目录（含 `dataset_info.json`、`data/intent_sft.json`、`intent_lora_sft.yaml`）
整体拷贝到 LLaMA-Factory 的 `data/` 目录约定位置，或在 `dataset_info.json`
中用绝对路径指向 `intent_sft.json`。

## 2. 训练

```bash
pip install llamafactory  # 或源码安装，见 requirements.txt 训练分区
llamafactory-cli train intent_lora_sft.yaml
```

关键超参（调优要点）：

| 超参 | 取值 | 理由 |
| --- | --- | --- |
| lora_rank / alpha | 16 / 32 | 1000 条小数据，rank 8-16 足够；alpha=2*rank |
| learning_rate | 1e-4 | 小数据 + 小模型，2e-4 易震荡，5e-5 收敛慢 |
| epochs | 3 | 验证集 loss 在第 3-4 轮后回升，早停于 3 |
| cutoff_len | 512 | 意图样本最长 ~60 字，512 绰绰有余 |
| val_size | 0.1 | 留出 100 条监控过拟合 |

## 3. 合并导出

```bash
llamafactory-cli export \
  --model_name_or_path Qwen/Qwen2.5-1.5B-Instruct \
  --adapter_name_or_path saves/qwen2.5-1.5b-intent/lora \
  --template qwen --finetuning_type lora \
  --export_dir models/intent-lora-merged --export_size 2 --export_legacy_format False
```

把导出的 `models/intent-lora-merged` 放回项目根目录（或设置
`INTENT_MODEL_PATH` 指向它），`LoraIntentRouter` 下次启动自动加载。

## 4. 评测

```python
# 评测脚本示意（在装有 transformers 的环境运行）
from src.intent.lora_router import LoraIntentRouter
from src.intent.prompt_router import PromptIntentRouter
from src.llm.client import MockLLM
import json

router = LoraIntentRouter("models/intent-lora-merged",
                          fallback=PromptIntentRouter(MockLLM()))
cases = [json.loads(l) for l in open("data/intent_samples.jsonl", encoding="utf-8")]
correct = sum(router.route(c["text"]).code == c["intent"] for c in cases)
print(f"accuracy = {correct / len(cases):.2%}")
```

## 5. 排错备忘

- **验证集准确率卡在 70%**：多半是训练/验证标签分布被 shuffle 破坏，
  检查 `val_size` 划分后各类意图是否均衡；
- **输出带多余解释文字**：确认 `template: qwen` 与基座模型一致，
  推理端用正则提取 `[A-Z_]+` 兜底（`lora_router.py` 已实现）；
- **显存不足**：`per_device_train_batch_size` 降到 4，梯度累积提到 8。
