# Evaluation README

`tests/eval/` 现在维护两条评测链路：

- `eval_owner_centered_add.py`
  - 主评测
  - 走真实 `Memory.add()` -> STL parse/store -> owner-centered projection 链路
- `eval_extraction.py`
  - legacy 回归
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
  - 仓库默认测试配置
  - 当前使用 `fake` LLM 和 `fake-embedding`
  - 适合本地快速验证，不消耗真实 API
- `mind.toml`
  - 你的本地开发配置
  - 可能连接真实 LLM / embedding / pgvector / qdrant

如果只是手动验证 runner 行为，优先使用 `mindt.toml`。

## 1. 主评测: Owner-Centered Add Eval

这条 runner 评估的是最终持久化结果，而不是中间抽取文本。每个 case 会：

1. 按顺序调用 `Memory.add()`
2. 检查当前 active memories
3. 检查 STL persisted `refs / statements / evidence`
4. 汇总 owner-centered 指标

### 跑全部 owner-centered 数据集

```bash
python tests/eval/runners/eval_owner_centered_add.py \
  --toml mindt.toml
```

不传 `--dataset` 时，会自动跑这些 STL-native 数据集：

- `tests/eval/datasets/owner_centered_add_cases.json`
- `tests/eval/datasets/owner_centered_feature_cases.json`
- `tests/eval/datasets/owner_centered_relationship_cases.json`

### 只跑一个数据集

```bash
python tests/eval/runners/eval_owner_centered_add.py \
  --toml mindt.toml \
  --dataset tests/eval/datasets/owner_centered_relationship_cases.json
```

### 打印完整 JSON summary

```bash
python tests/eval/runners/eval_owner_centered_add.py \
  --toml mindt.toml \
  --dataset tests/eval/datasets/owner_centered_feature_cases.json \
  --pretty
```

### 开启并发

```bash
python tests/eval/runners/eval_owner_centered_add.py \
  --toml mind.toml \
  --dataset tests/eval/datasets/owner_centered_relationship_cases.json \
  --concurrency 4
```

说明：

- 适合手动跑真实模型时提速
- 默认 `--concurrency 1`
- 每个 case 都会使用独立临时存储，避免互相污染

Owner-centered runner 关注的指标主要有：

- `canonical_text_accuracy`
- `subject_ref_accuracy`
- `count_accuracy`
- `owner_accuracy`
- `ref_accuracy`
- `statement_accuracy`
- `evidence_accuracy`
- `update_accuracy`
- `case_pass_rate`

三套 STL-native 数据集的定位：

- `owner_centered_add_cases.json`
  - 基础 add / self / relation / update 回归
- `owner_centered_feature_cases.json`
  - STL frame 语义专项
  - 当前覆盖 `hope / say / believe / if`
- `owner_centered_relationship_cases.json`
  - owner-centered 关系投影专项
  - 覆盖 named / inverse / split / stable relation 等典型模式

## 2. Legacy: Extraction Eval

这条 runner 还保留着，用来回归 `_extract_facts()` 的旧 contract，但它不再是 STL 主验收路径。

### 跑全部 extraction 数据集

```bash
python tests/eval/runners/eval_extraction.py --toml mindt.toml
```

默认会跑：

- `tests/eval/datasets/extraction_curated_cases.json`
- `tests/eval/datasets/extraction_relationship_cases.json`

### 只跑一个 extraction 数据集

```bash
python tests/eval/runners/eval_extraction.py \
  --toml mindt.toml \
  --dataset tests/eval/datasets/extraction_curated_cases.json
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

Extraction eval 关注的指标主要有：

- `recall`
- `precision`
- `no_extract_accuracy`
- `confidence_accuracy`
- `count_accuracy`

如果数据集包含关系注解，还会额外评估：

- `relation_recall`
- `relation_forbidden_accuracy`
- `relation_case_accuracy`

## 3. 用真实模型手动评测

如果你想用真实模型，只要把 `--toml` 换成你的真实配置：

```bash
python tests/eval/runners/eval_owner_centered_add.py \
  --toml mind.toml \
  --dataset tests/eval/datasets/owner_centered_relationship_cases.json
```

或者：

```bash
python tests/eval/runners/eval_extraction.py \
  --toml mind.toml \
  --dataset tests/eval/datasets/extraction_relationship_cases.json
```

注意：

- owner-centered runner 评的是完整 add 链路，耗时会高于 extraction-only
- extraction runner 会使用 `[llm.extraction]`，如果没配则回退到 `[llm]`
- 使用真实模型会有耗时和费用

## 4. 如何看结果

运行后会先打印一段 summary，然后把详细 JSON 写到 `tests/eval/reports/`。

常见检查方式：

1. 看 summary 里哪些指标是 `FAIL`
2. 看 `failed cases`
3. 打开对应 JSON 报告，定位具体 case 的 `failures`

owner-centered 报告里重点看：

- `expected_active_memories`
- `expected_refs`
- `expected_statements`
- `expected_evidence`
- `expected_versioned_active_memories`

extraction 报告里重点看：

- `missing`
- `forbidden`
- `count`

## 5. 跑对应的 Pytest

如果你改了 owner-centered runner 或 STL-native 数据集，建议跑：

```bash
pytest -q tests/test_eval_owner_centered_add.py
```

如果你改了 fake LLM、`Memory.add()`、或 STL 投影逻辑，建议再补：

```bash
pytest -q tests/test_fake_llm.py tests/test_memory.py
```

补充说明：

- 常规 pytest 默认应走 `tests/conftest.py` 里的显式 fake 覆盖
- 不应该依赖 `mindt.toml` 恰好配置成 fake，测试代码本身要明确声明自己不需要真实 LLM

如果你改了 extraction runner 或 extraction 数据集，建议跑：

```bash
pytest -q tests/test_eval_extraction.py
```

## 6. 常见建议

- 想验证 STL 主链路，优先看 owner-centered add eval
- 想回归 `_extract_facts()` 旧行为，再看 extraction eval
- 想快速跑本地 deterministic 验证，优先用 `mindt.toml`
