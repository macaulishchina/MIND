# Evaluation README

`tests/eval/` 目前主要有两类手动评测脚本：

- `eval_owner_centered_add.py`
  - 主评测
  - 走真实 `Memory.add()` -> STL parse/store -> owner-centered projection 全链路
- `eval_llm_speed.py`
  - LLM 延迟测速
  - 可测简单对话，也可单独测 `stl_extraction` / `decision` 阶段

## 目录

- 案例文件: `tests/eval/cases/<suite>/<case-id>.json`
- 套件元数据: `tests/eval/cases/<suite>/_suite.json`
- 运行脚本: `tests/eval/runners/`
- 输出报告: `tests/eval/reports/`

## 先看怎么选

如果你只是想做快速验证，先按下面选：

- 想测业务主链路结果是否正确：用 `eval_owner_centered_add.py`
- 想测模型回一个短句有多快：用 `eval_llm_speed.py --stage llm`
- 想单独测 STL 抽取阶段速度：用 `eval_llm_speed.py --stage stl_extraction`
- 想单独测 decision 阶段速度：用 `eval_llm_speed.py --stage decision`
- 想跑离线回归测试：优先用 `pytest`

## 前置条件

1. 进入仓库根目录：

```bash
cd /home/huyidong/workspace/MIND
```

2. 准备配置文件：

- `mindt.toml`
  - 仓库默认测试配置
  - 本地依赖更轻，适合手动验证 runner 行为
- `mind.toml`
  - 你的本地开发配置
  - 可能连接真实 LLM / embedding / pgvector / qdrant

建议：

- 只想验证脚本行为，优先用 `mindt.toml`
- 想测真实模型响应或真实链路，使用 `mind.toml`
- 想完全避免真实模型调用，优先使用 pytest 里的 fake 覆盖

## 1. LLM 延迟测速

`eval_llm_speed.py` 用来回答一个更直接的问题：

- 一个简单对话要多久
- 某个内部 LLM stage 要多久

它不会写 `tests/eval/reports/` 文件，结果直接打印到终端，最后一行会输出 JSON summary。

### 最简单的对话测速

这是最基础的“打个招呼”测试：

```bash
python tests/eval/runners/eval_llm_speed.py \
  --toml mind.toml \
  --stage llm \
  --text hi \
  --runs 3
```

这个命令的含义是：

- 使用 `mind.toml` 里的默认 LLM 配置
- 不走 `Memory.add()` 链路
- 直接发 3 次简单用户消息 `hi`
- 统计最小、最大、平均、中位耗时

适合做：

- 最基础的连通性检查
- 首次判断“模型是不是明显过慢”
- 更换 provider 或 model 后做快速对比

### 测 STL 抽取阶段速度

```bash
python tests/eval/runners/eval_llm_speed.py \
  --toml mind.toml \
  --stage stl_extraction \
  --conversation 'User: My coworker Dana drinks oat milk every morning' \
  --runs 5
```

适合在你怀疑 STL prompt、模型选择或 batch 设置影响速度时使用。

### 测 decision 阶段速度

```bash
python tests/eval/runners/eval_llm_speed.py \
  --toml mind.toml \
  --stage decision \
  --existing-memories '[0] [friend:green] relation_to_owner=friend' \
  --new-fact '[friend:green] occupation=football player' \
  --runs 5
```

适合单独观察 update / merge 决策阶段的延迟。

### 做本地 fake sanity check

```bash
python tests/eval/runners/eval_llm_speed.py \
  --toml mindt.toml \
  --stage stl_extraction \
  --provider fake \
  --model fake-memory-test \
  --runs 1
```

### 常用参数

- `--toml`: 使用哪个配置文件
- `--stage`: `llm` / `stl_extraction` / `decision`
- `--text`: 仅 `--stage llm` 使用，表示简单对话的用户输入
- `--runs`: 正式计时次数
- `--warmup`: 预热次数，怀疑首包慢时可加 `--warmup 1`
- `--provider`: 临时覆盖 provider
- `--model`: 临时覆盖 model
- `--temperature`: 临时覆盖 temperature
- `--batch`: 临时覆盖 batch 开关
- `--show-response`: 打印每次完整响应

### 测速输出怎么看

终端会打印：

- 当前实际使用的 `provider / protocols / model / batch / temperature`
- 每次调用耗时
- 响应长度和预览
- `min / max / avg / median`
- 最后一行 JSON summary

如果你只想知道“现在模型回一句 hi 要多久”，重点看：

- `avg_s`
- `median_s`

## 2. Owner-Centered Add 评测

`eval_owner_centered_add.py` 评估的是最终持久化结果，不是中间 prompt 文本。

每个 case 会：

1. 先把 case 的 `turns` 展平成一个按原顺序排列的 message 列表
2. 只调用一次 `Memory.add()`
3. 检查当前 active memories
4. 检查 STL persisted `refs / statements / evidence`
5. 汇总 owner-centered 指标

### 什么时候用它

适合这些场景：

- 改了 `Memory.add()`
- 改了 STL parse/store
- 改了 owner-centered projection
- 改了单次对话片段提交后的最终落库结果
- 想确认最终写入系统的数据是否正确

### 跑全部数据集

```bash
python tests/eval/runners/eval_owner_centered_add.py \
  --toml mindt.toml
```

默认会自动跑 `tests/eval/cases/` 下全部案例文件：

- `owner-add-*` — 基础 add / self / relation / chunk-final-state
- `owner-feature-*` — STL frame 语义
- `owner-rel-*` — 关系投影稳定性

### 只跑单个案例

```bash
python tests/eval/runners/eval_owner_centered_add.py \
  --toml mindt.toml \
  --case tests/eval/cases/owner-add-001.json
```

### 打印更易读的 JSON 输出

```bash
python tests/eval/runners/eval_owner_centered_add.py \
  --toml mindt.toml \
  --case tests/eval/cases/owner-feature-003.json \
  --pretty
```

### 用真实模型并发跑

```bash
python tests/eval/runners/eval_owner_centered_add.py \
  --toml mind.toml \
  --case tests/eval/cases/owner-rel-stable-001.json \
  --concurrency 4
```

说明：

- 默认 `--concurrency 1`
- 手动跑真实模型时可以适当提速
- 每个 case 使用独立临时存储，避免互相污染

## 3. 这条主评测到底在看什么

它不是在看“模型抽得像不像”，而是在看“系统最后写进去的结果对不对”。

重点包括：

- owner 解析是否正确
- `refs / statements / evidence` 是否保留下来
- `subject_ref` 是否稳定
- `canonical_text` 是否符合预期
- 单次提交的多轮内容是否只留下最终有效结果
- `hope / say / believe / if` 这类 frame 语义是否在 STL persisted state 中保留

### 三套数据集分别关注什么

- `cases/add/`
  - 基础 add / self / relation / chunk-final-state 回归
  - 用来判断主链是否正常
- `cases/feature/`
  - STL frame 语义专项
  - 用来判断 richer STL 结构有没有丢
- `cases/relationship/`
  - owner-centered 关系投影专项
  - 用来判断第三方关系投影是否稳定

可以粗略记成：

- `add`: 主链回归
- `feature`: STL 结构语义
- `relationship`: 关系投影稳定性

## 4. 主评测的输入和输出

### 输入

CLI 主要参数：

- `--toml`: 运行 `Memory` 的配置文件
- `--case`: 单个案例 JSON 文件
- `--output`: JSON 报告输出位置
- `--concurrency`: case 并发数
- `--pretty`: 是否格式化 JSON 输出
- `--fail-on-targets`: 只要有指标低于目标值就返回非零退出码

数据集中的每个 case 主要包含：

- `owner`
- `turns`
  - 仅用于表达对话顺序和轮次结构，不代表多次 `Memory.add()`
- `expected_active_count`
- `expected_active_memories`
- `expected_refs`
- `expected_statements`
- `expected_evidence`

### 输出

runner 会产出两份结果：

- 终端 summary
- JSON 报告，默认写到 `tests/eval/reports/<dataset>_report.json`

JSON 顶层字段主要有：

- `dataset`
- `dataset_name`
- `toml_path`
- `total_cases`
- `targets`
- `metrics`
- `cases`

汇总指标主要有：

- `canonical_text_accuracy`
- `subject_ref_accuracy`
- `count_accuracy`
- `owner_accuracy`
- `ref_accuracy`
- `statement_accuracy`
- `evidence_accuracy`
- `case_pass_rate`

## 5. 如何看结果

如果是 `eval_llm_speed.py`：

- 看终端里的 `avg_s` 和 `median_s`
- 想做不同模型对比，就固定输入，多跑几次

如果是 `eval_owner_centered_add.py`：

1. 先看 summary 里哪些指标是 `FAIL`
2. 再看 `failed cases`
3. 最后打开对应 JSON 报告定位具体 `failures`

主评测里最值得优先检查的是：

- `expected_active_memories`
- `expected_refs`
- `expected_statements`
- `expected_evidence`

## 6. 对应的 Pytest

如果你改了评测 runner 或 STL-native 数据集，建议跑：

```bash
pytest -q tests/test_eval_owner_centered_add.py
```

如果你改了 fake LLM、`Memory.add()` 或 STL 投影逻辑，建议再补：

```bash
pytest -q tests/test_fake_llm.py tests/test_memory.py
```

补充说明：

- 常规 pytest 默认应走 `tests/conftest.py` 里的显式 fake 覆盖
- 不应该依赖 `mindt.toml` 的默认 provider 是什么
- 测试代码本身应明确声明自己不需要真实 LLM
