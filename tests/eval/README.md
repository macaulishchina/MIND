# Evaluation README

`tests/eval/` 当前只维护一条评测链路：

- `eval_owner_centered_add.py`
  - 主评测
  - 走真实 `Memory.add()` -> STL parse/store -> owner-centered projection 链路

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
  - 仍保留更轻量的本地存储 / embedding 配置，适合手动评测时减少外围依赖
- `mind.toml`
  - 你的本地开发配置
  - 可能连接真实 LLM / embedding / pgvector / qdrant

如果只是手动验证 runner 行为，优先使用 `mindt.toml`。
如果想完全避免真实模型调用，使用 pytest 里的显式 fake 覆盖，或手动传入 fake 配置。
默认 TOML 已不再展开 legacy `llm.extraction / llm.normalization` stage；主链相关的可选 stage override 只有 `llm.stl_extraction` 和 `llm.decision`。

## 1. Owner-Centered Add Eval

这条 runner 评估的是最终持久化结果，而不是中间抽取文本。每个 case 会：

1. 按顺序调用 `Memory.add()`
2. 检查当前 active memories
3. 检查 STL persisted `refs / statements / evidence`
4. 汇总 owner-centered 指标

### 这条测试的输入是什么

runner 的输入有两层：

- CLI 输入
  - `--toml`: 运行 `Memory` 的配置文件
  - `--dataset`: 要评测的数据集 JSON 文件，或一个包含多个数据集的目录
  - `--output`: JSON 报告输出位置
  - `--concurrency`: case 并发数
  - `--pretty`: 是否格式化输出 JSON
  - `--fail-on-targets`: 只要有指标低于目标值就返回非零退出码

- 数据集输入
  - 每个数据集是一个 JSON 文件，顶层包含 `name / focus / description / cases`
  - 每个 `case` 的真实输入主要是：
    - `owner`: 当前对话属于谁，支持 `external_user_id` 或 `anonymous_session_id`
    - `turns`: 多轮对话输入。每个 turn 会原样传给 `Memory.add()`
  - 每个 `case` 的断言输入主要是：
    - `expected_active_count`
    - `expected_active_memories`
    - `expected_refs`
    - `expected_statements`
    - `expected_evidence`
    - `expected_deleted_memories`
    - `expected_versioned_active_memories`

一个最小 case 可以理解成：

```json
{
  "id": "owner-add-001",
  "description": "self facts become canonical self memories",
  "owner": {
    "external_user_id": "eval_known_self_001"
  },
  "turns": [
    {
      "messages": [
        {
          "role": "user",
          "content": "My name is John and I am 30 years old"
        }
      ]
    }
  ],
  "expected_active_count": 2,
  "expected_active_memories": [
    {"canonical_text": "[self] name=John"},
    {"canonical_text": "[self] age=30"}
  ],
  "expected_statements": [
    {"predicate": "name", "args": ["@self", "John"]},
    {"predicate": "age", "args": ["@self", 30]}
  ]
}
```

意思是：

- 输入一段对话给 `Memory.add()`
- 然后检查最终投影出来的 memory 和 STL store 里的结构化结果是不是符合预期

### 这条测试的输出是什么

runner 会产出两份结果：

- 终端 summary
  - 每个数据集一段文本摘要
  - 包括 `dataset / focus / config / total cases / metrics / failed cases / json report saved to`

- JSON 报告
  - 默认写到 `tests/eval/reports/<dataset>_report.json`
  - 顶层字段主要有：
    - `dataset`
    - `dataset_name`
    - `dataset_focus`
    - `dataset_description`
    - `toml_path`
    - `total_cases`
    - `targets`
    - `metrics`
    - `cases`
  - `metrics` 里是汇总指标：
    - `canonical_text_accuracy`
    - `subject_ref_accuracy`
    - `count_accuracy`
    - `owner_accuracy`
    - `ref_accuracy`
    - `statement_accuracy`
    - `evidence_accuracy`
    - `update_accuracy`
    - `case_pass_rate`
  - `cases` 里是逐 case 诊断信息：
    - `id`
    - `description`
    - `failures`
    - `active_memories`
    - `current_statements`
    - `refs`
    - `evidence`

换句话说，这条 runner 不输出“模型原始回复对不对”，而是输出“经过 `Memory.add()` 完整链路后，最终持久化状态对不对”。

### 这条测试到底在考什么

它考察的是 STL-native `Memory.add()` 的端到端业务结果，不是 prompt 层的中间文本质量。重点包括：

- owner 解析是否正确
  - known owner / anonymous owner 是否复用到同一个 owner 空间

- STL 抽取是否保留了正确结构
  - `refs`
  - `statements`
  - `evidence`

- owner-centered projection 是否正确
  - `subject_ref` 是否稳定
  - `canonical_text` 是否符合预期
  - `field_key / fact_family / relation_type` 是否对

- update 行为是否正确
  - 单值字段是否 update
  - 老 memory 是否进入 deleted
  - 新 memory 是否带 `version_of`

- frame 语义是否没有在投影前丢失
  - `hope / say / believe / if` 这类 frame 至少要在 STL persisted state 里存在

所以它的本质不是“测抽取了多少条”，而是“测业务链路最后写进系统里的东西是否正确”。

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
  - 主要考主链是否能正确把普通用户事实落成 active memories
  - 适合改了 `Memory.add()`、投影逻辑、update 逻辑后先回归
- `owner_centered_feature_cases.json`
  - STL frame 语义专项
  - 当前覆盖 `hope / say / believe / if`
  - 主要考 richer STL 结构有没有被 parse/store 保留下来
  - 即使 active memories 不是重点，这套也要求 `refs / statements / evidence` 正确
- `owner_centered_relationship_cases.json`
  - owner-centered 关系投影专项
  - 覆盖 named / inverse / split / stable relation 等典型模式
  - 主要考第三方关系的 subject 稳定性和投影正确性
  - 适合改了 relation projection、focus、subject_ref 映射时重点看

可以把三套数据集粗略理解成：

- `add_cases`: 测主链是否能正常工作
- `feature_cases`: 测 STL 结构语义有没有丢
- `relationship_cases`: 测第三方关系投影是不是稳定

## 2. 用真实模型手动评测

如果你想用真实模型，只要把 `--toml` 换成你的真实配置：

```bash
python tests/eval/runners/eval_owner_centered_add.py \
  --toml mind.toml \
  --dataset tests/eval/datasets/owner_centered_relationship_cases.json
```

注意：

- owner-centered runner 评的是完整 add 链路
- 使用真实模型会有耗时和费用
- 如需提速，优先配合 `--concurrency`
- 它会按 `--toml` 里的 `[logging]` 配置输出运行日志；如果 `verbose=true`，会继续打印更详细的 prompt / output 明细

## 3. 单独测 LLM 响应速度

如果你只是想知道 LLM 回一个很短输入要多久，比如你发一个 `hi`，可以直接这样跑：

```bash
python tests/eval/runners/eval_llm_speed.py \
  --toml mind.toml \
  --stage llm \
  --text hi \
  --runs 3
```

如果你还想继续细分到某个内部 LLM stage，不想先跑完整数据集，也可以用同一个 runner：

```bash
python tests/eval/runners/eval_llm_speed.py \
  --toml mind.toml \
  --stage stl_extraction \
  --runs 3
```

它会直接对一个 LLM stage 连续发请求，并打印：

- 当前使用的 `provider / protocols / model / batch / temperature`
- 每次调用耗时
- 响应字符数和预览
- `min / max / avg / median`

这个测速 runner 不会写 `tests/eval/reports/` 文件；最后一行会直接在 stdout 打印一段 JSON summary，方便你临时重定向保存。
调用过程中的 `🧠 [LLM]` 日志和 verbose 明细走的是同一个 `[logging]` 配置，不依赖是否经过 `Memory.add()`。

常见用法：

- 测 STL 抽取速度

```bash
python tests/eval/runners/eval_llm_speed.py \
  --toml mind.toml \
  --stage stl_extraction \
  --conversation 'User: My coworker Dana drinks oat milk every morning' \
  --runs 5
```

- 测 decision 阶段速度

```bash
python tests/eval/runners/eval_llm_speed.py \
  --toml mind.toml \
  --stage decision \
  --existing-memories '[0] [friend:green] relation_to_owner=friend' \
  --new-fact '[friend:green] occupation=football player' \
  --runs 5
```

- 只做本地 fake sanity check

```bash
python tests/eval/runners/eval_llm_speed.py \
  --toml mindt.toml \
  --stage stl_extraction \
  --provider fake \
  --model fake-memory-test \
  --runs 1
```

如果你怀疑是首包慢，可以加 `--warmup 1` 先预热一次。

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
- 不应该依赖 `mindt.toml` 的默认 provider 是什么，测试代码本身要明确声明自己不需要真实 LLM

## 6. 常见建议

- 想验证业务主链路，优先看 owner-centered add eval
- 想先确认“模型本身是不是太慢”，先跑 `eval_llm_speed.py`
- 想跑常规离线测试，优先用 pytest，因为测试夹具会显式切 fake
- 想手动跑 add 评测且减少外围依赖，优先用 `mindt.toml`
