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
  - 评估 STL 抽取结果中的 `refs / statements`

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
- `--model`: 覆盖模型名称

---

## STL 提示词 A/B 测试

入口：`tests/eval/runners/eval_stl_ab.py`

用于比较 STL 抽取提示词的两种配置：

| Arm | 提示词 | 说明 |
|-----|--------|------|
| A | 基础提示词 | `stl_extraction_supplement = false` |
| B | 基础 + 补充提示词 | `stl_extraction_supplement = true` |

每个 arm 可以使用不同模型，支持「强模型 + 基础提示词 vs 弱模型 + 扩展提示词」等对比场景。

### 评测模式

根据 case 数据自动选择评测方式：

1. **Structured**（结构化匹配）— case 包含 `stages.stl_extract.expected_refs / expected_statements` 时使用，按 ref/statement 命中率计分
2. **LLM-as-Judge**（裁判评分）— case 包含 `golden_stl` 且指定 `--judge` 模型时使用，7 个维度加权评分：
   - completeness (20%) / predicate_choice (15%) / argument_correctness (15%)
   - correction_handling (15%) / modifier_attachment (10%)
   - no_hallucination (15%) / format_compliance (10%)
3. **Parse-only**（仅解析）— 无断言数据时回退，比较 statement 数和 parse 失败数

### Case 数据源

| 目录 | 格式 | 评测方式 |
|------|------|----------|
| `tests/eval/cases/` | `stages.stl_extract` | Structured |
| `tests/eval/prompt_opt/cases/` | `golden_stl` | LLM-as-Judge |

`prompt_opt/cases/` 下有 20 个 case（po-basic-001 ~ po-vibecoding-001），覆盖基础对话、纠正、否定、多事件、长对话等场景。

### 运行方式

#### 1. 同模型 A/B（结构化评测）

```bash
python tests/eval/runners/eval_stl_ab.py \
  --toml mindt.toml \
  --model gpt-5.4-nano \
  --case tests/eval/cases/
```

#### 2. 同模型 A/B（裁判评分）

```bash
python tests/eval/runners/eval_stl_ab.py \
  --toml mindt.toml \
  --model gpt-5.4-nano \
  --judge gpt-5.4-nano
```

默认使用 `tests/eval/prompt_opt/cases/` 下的全部 case。

#### 3. 跨模型 A/B

```bash
python tests/eval/runners/eval_stl_ab.py \
  --toml mindt.toml \
  --model-a claude-opus-4-6 \
  --model-b gpt-5.4-nano \
  --judge gpt-5.4-nano
```

#### 4. 单个 case 调试

```bash
python tests/eval/runners/eval_stl_ab.py \
  --toml mindt.toml \
  --model gpt-5.4-nano \
  --case tests/eval/prompt_opt/cases/po-basic-001.json \
  --judge gpt-5.4-nano
```

#### 5. JSON 报告输出

```bash
python tests/eval/runners/eval_stl_ab.py \
  --toml mindt.toml \
  --model gpt-5.4-nano \
  --judge gpt-5.4-nano \
  --json --output tests/eval/reports/stl_ab.json
```

#### 6. 快速验证（跳过裁判，只跑前 5 个 case）

```bash
python tests/eval/runners/eval_stl_ab.py \
  --toml mindt.toml \
  --model gpt-5.4-nano \
  --skip-judge --limit 5
```

#### 7. 并发加速（case 级别并行）

```bash
python tests/eval/runners/eval_stl_ab.py \
  --toml mindt.toml \
  --model gpt-5.4-nano \
  --judge gpt-5.4-nano \
  --concurrency 4
```

常用参数：

- `--model`: 两个 arm 使用同一模型
- `--model-a` / `--model-b`: 分别指定 A/B arm 的模型
- `--judge`: 裁判模型（需要 case 包含 `golden_stl`）
- `--skip-judge`: 跳过裁判评分，只做提取和解析
- `--limit N`: 只跑前 N 个 case（快速验证）
- `--concurrency N`: case 级别并发数（默认 1）
- `--case`: 单个 case 文件或目录
- `--toml`: 配置文件
- `--json`: 输出 JSON 格式
- `--output`: 报告写入文件路径

### 并发架构

每个 case 内部已实现两级并发：
1. **提取并发**: Arm A 和 Arm B 的 LLM 提取同时进行
2. **裁判并发**: 两个 arm 的裁判评分同时进行

`--concurrency N` 额外在 case 级别并行，N 个 case 同时处理。
总并发 LLM 请求数 = concurrency × 2（提取阶段）或 concurrency × 2（裁判阶段）。

### 配置

提示词补充开关通过 TOML 配置：

```toml
[prompts]
stl_extraction_supplement = false   # true 启用扩展提示词
```

A/B 测试中 Arm A 强制 `supplement=false`，Arm B 强制 `supplement=true`，不受配置文件影响。

---

## Prompt Optimization 工具

入口：`tests/eval/prompt_opt/`

用于 STL 提示词的多模型对比和质量评估。

### 目录结构

- `cases/` — 20 个评测 case (含 `golden_stl`)
- `judge.py` — LLM-as-Judge 评分器
- `runner.py` — 单模型批量运行
- `run_model_comparison.py` — 多模型速度对比
- `run_quality_eval.py` — 多模型质量评估
- `results/` / `results_r2/` — 历史结果
- `REPORT.md` — 评测报告

---

## 单条 STL 调试

入口：`tests/eval/runners/eval_stl_extract.py`

对单条对话进行 STL 抽取并打印解析结果，仅用于调试观察，不做 pass/fail 判定。

```bash
python tests/eval/runners/eval_stl_extract.py \
  --toml mindt.toml \
  --input "用户: 我喜欢吃火锅"
```
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
