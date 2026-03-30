# Evaluation README

`tests/eval/` 当前维护的是 extraction 评测：

- `eval_extraction.py`
  - 只评估 `_extract_facts()` 抽取阶段

## 目录

- 数据集: `tests/eval/datasets/`
- 运行脚本: `tests/eval/runners/`
- 输出报告: `tests/eval/reports/`

## 前置条件

1. 进入仓库根目录：

```bash
cd /home/macaulish/workspace/MIND
```

2. 准备配置文件：

- `mindt.toml`
  - 本仓库默认测试配置
  - 当前使用 `fake` LLM 和 `fake-embedding`
  - 适合本地快速验证，不消耗真实 API
- `mind.toml`
  - 你的本地开发配置
  - 可能连接真实 LLM / embedding / pgvector / qdrant

如果只是手动验证 runner 行为，建议先用 `mindt.toml`。

## 1. 手动跑 Extraction Eval

### 跑全部 extraction 数据集

```bash
python tests/eval/runners/eval_extraction.py --toml mindt.toml
```

说明：

- 不传 `--dataset` 时，会自动跑这两个维护中的 extraction 数据集：
  - `tests/eval/datasets/extraction_curated_cases.json`
  - `tests/eval/datasets/extraction_relationship_cases.json`
- JSON 报告会写到 `tests/eval/reports/`

### 只跑一个数据集

```bash
python tests/eval/runners/eval_extraction.py \
  --toml mindt.toml \
  --dataset tests/eval/datasets/extraction_curated_cases.json
```

### 跑关系专项 extraction 数据集

```bash
python tests/eval/runners/eval_extraction.py \
  --toml mindt.toml \
  --dataset tests/eval/datasets/extraction_relationship_cases.json
```

### 开启并发

```bash
python tests/eval/runners/eval_extraction.py \
  --toml mindt.toml \
  --concurrency 4
```

### 当指标不达标时返回非 0

```bash
python tests/eval/runners/eval_extraction.py \
  --toml mindt.toml \
  --fail-on-targets
```

### 打印完整 JSON

```bash
python tests/eval/runners/eval_extraction.py \
  --toml mindt.toml \
  --dataset tests/eval/datasets/extraction_relationship_cases.json \
  --pretty
```

Extraction Eval 关注的指标主要有：

- `recall`
- `precision`
- `no_extract_accuracy`
- `confidence_accuracy`
- `count_accuracy`

如果数据集包含关系注解，还会额外评估：

- `relation_recall`
- `relation_forbidden_accuracy`
- `relation_case_accuracy`

两套 extraction 数据集的定位：

- `extraction_curated_cases.json`
  - 100 条通用回归集
  - 来自旧 easy / medium / hard / tricky / blackbox 的合并精选版
  - 适合看总体事实抽取、排除、数量控制是否退化
- `extraction_relationship_cases.json`
  - 100 条关系专项集
  - 全部都是带关系的问题，专门看 LLM 对 relation-bearing 输入的提取能力
  - 覆盖 named / unnamed、正向 / 逆向表达、中英双语、多轮复用、同名不同关系、以及关系负例

## 2. 用真实模型手动评测

如果你想用真实模型，只要把 `--toml` 换成你的真实配置：

```bash
python tests/eval/runners/eval_extraction.py \
  --toml mind.toml \
  --dataset tests/eval/datasets/extraction_relationship_cases.json
```

注意：

- `eval_extraction.py` 会使用 `[llm.extraction]`，如果没配则回退到 `[llm]`
- 使用真实模型会有耗时和费用

## 3. 如何看结果

运行后会先打印一段 summary，然后把详细 JSON 写到 `tests/eval/reports/`。

常见检查方式：

1. 看 summary 里哪些指标是 `FAIL`
2. 看 `failed cases`
3. 打开对应 JSON 报告，定位具体 case 的 `failures`

比如：

- extraction 报告里重点看 `missing`、`forbidden`、`count`

## 4. 跑对应的 Pytest

如果你改了 runner 或数据集，建议顺手跑这些测试：

```bash
pytest -q tests/test_eval_extraction.py
```

如果你改动了 `Memory._extract_facts()` 或相关抽取逻辑，建议再补：

```bash
pytest -q tests/test_extraction.py tests/test_memory.py
```

## 5. 常见建议

- 想快速看脚本逻辑是否通，优先用 `mindt.toml`
- 想看真实效果，再切到 `mind.toml`
- 调整 extraction 模型时，先看 extraction eval
