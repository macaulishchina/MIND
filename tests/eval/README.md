# Evaluation README

`tests/eval/` 现在围绕一个共享 case 数据集和一个统一 stage runner 组织。

主入口：

- `eval_cases.py`
  - 正式评测入口
  - 统一 CLI
  - 通过 `--stage` 选择评测阶段
- `eval_stl_extract.py`
  - 单 case / 单段对话观察器
  - 只用于调试 STL 抽取，不承担正式 pass/fail 评测

## 目录

- 案例文件: `tests/eval/cases/*.json`
- 运行脚本: `tests/eval/runners/`
- 输出报告: `tests/eval/reports/`

## Case Schema

所有 case 共享一套输入结构：

- `id`
- `suite`
- `description`
- `owner`
- `turns`
- `stages`

其中：

- `turns` 只负责表达对话顺序和轮次结构
- `stages.<stage-name>` 负责表达阶段专属断言
- 同一个 case 可以同时被多个 stage 复用，不重复写对话输入

当前支持的 stage：

- `stages.owner_add`
  - 评估 `Memory.add()` 之后的最终 owner-centered memory state
- `stages.stl_extract`
  - 评估 STL 抽取结果中的 `refs / statements / evidence`

## 统一运行方式

### 1. Owner Add 阶段

```bash
python tests/eval/runners/eval_cases.py \
  --stage owner_add \
  --toml mindt.toml
```

### 2. STL Extract 阶段

```bash
python tests/eval/runners/eval_cases.py \
  --stage stl_extract \
  --toml mindt.toml
```

### 3. 只跑单个 case

```bash
python tests/eval/runners/eval_cases.py \
  --stage owner_add \
  --toml mindt.toml \
  --case tests/eval/cases/owner-add-005.json
```

### 4. 生成更易读的 JSON 报告

```bash
python tests/eval/runners/eval_cases.py \
  --stage stl_extract \
  --toml mindt.toml \
  --case tests/eval/cases/owner-feature-001.json \
  --pretty
```

### 5. 真实模型并发跑

```bash
python tests/eval/runners/eval_cases.py \
  --stage owner_add \
  --toml mind.toml \
  --concurrency 4
```

常用参数：

- `--stage`: `owner_add` 或 `stl_extract`
- `--toml`: 运行配置
- `--case`: 单个 case 文件或 case 目录
- `--output`: JSON 报告输出路径或目录
- `--pretty`: 格式化 JSON 输出
- `--concurrency`: case 并发数
- `--fail-on-targets`: 指标未达标时返回非零退出码
- `--provider`: 覆盖 provider
- `--model`: 覆盖 model

## 两个 Stage 分别看什么

### `owner_add`

关注最终写入后的 owner-centered memory state：

- `expected_active_count`
- `expected_active_memories`

该阶段会：

1. 展平一个 case 的全部 `turns`
2. 只调用一次 `Memory.add()`
3. 校验最终 active memories

### `stl_extract`

关注 STL 抽取阶段的结构化结果：

- `expected_refs`
- `expected_statements`
- `expected_evidence`

该阶段不会走完整 memory 写入链路，而是直接评估 STL 抽取结果。

## 调试观察器

如果你想看“这段输入具体被抽成了什么 STL”，用：

```bash
python tests/eval/runners/eval_stl_extract.py \
  --toml mindt.toml \
  --case tests/eval/cases/owner-feature-001.json
```

也可以直接传一段对话：

```bash
python tests/eval/runners/eval_stl_extract.py \
  --toml mindt.toml \
  --conversation 'User: I hope Tom comes to Tokyo'
```

这个脚本会读取 `stages.stl_extract` 里的 expected 区块，方便你对照观察，但它不是主评测入口。

## 推荐 Pytest

如果你改了 eval case schema、共享 loader 或 stage 选择逻辑：

```bash
pytest -q tests/test_eval_dataset.py
```

如果你改了 owner add 阶段：

```bash
pytest -q tests/test_eval_stage_owner_add.py
```

如果你改了 STL extract 阶段：

```bash
pytest -q tests/test_eval_stage_stl_extract.py
```

如果你改了 fake LLM、`Memory.add()` 或 runtime logging，建议再补：

```bash
pytest -q tests/test_fake_llm.py tests/test_memory.py tests/test_runtime_logging.py
```
