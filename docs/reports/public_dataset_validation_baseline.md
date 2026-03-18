# Public Dataset Validation Baseline

验收日期：`2026-03-17`

验收对象版本：

- `git HEAD = aafff3d`
- 本报告对应对象为 public-dataset adapter / loader / unified evaluation / report CLI 首轮落地后的本地工作树

数据 / fixture 版本：

- `LoCoMo local-slice-v1`
- `HotpotQA local-slice-v1`
- `SciFact local-slice-v1`

验收对象：

- [PLANS.md](../../PLANS.md)
- [cli_ops_cmds.py](../../mind/cli_ops_cmds.py)
- [cli_phase_gates.py](../../mind/cli_phase_gates.py)
- [__init__.py](../../mind/fixtures/__init__.py)
- [__init__.py](../../mind/fixtures/public_datasets/__init__.py)
- [contracts.py](../../mind/fixtures/public_datasets/contracts.py)
- [compiler.py](../../mind/fixtures/public_datasets/compiler.py)
- [registry.py](../../mind/fixtures/public_datasets/registry.py)
- [source_loader.py](../../mind/fixtures/public_datasets/source_loader.py)
- [evaluation.py](../../mind/fixtures/public_datasets/evaluation.py)
- [raw_import.py](../../mind/fixtures/public_datasets/raw_import.py)
- [run_public_dataset_eval.py](../../scripts/run_public_dataset_eval.py)
- [compile_public_dataset_slice.py](../../scripts/compile_public_dataset_slice.py)
- [test_public_dataset_adapters.py](../../tests/test_public_dataset_adapters.py)
- [test_public_dataset_loaders.py](../../tests/test_public_dataset_loaders.py)
- [test_public_dataset_evaluation.py](../../tests/test_public_dataset_evaluation.py)
- [test_public_dataset_raw_import.py](../../tests/test_public_dataset_raw_import.py)

相关工件：

- [locomo_report.json](../../artifacts/dev/public_datasets/locomo_report.json)
- [hotpotqa_report.json](../../artifacts/dev/public_datasets/hotpotqa_report.json)
- [scifact_report.json](../../artifacts/dev/public_datasets/scifact_report.json)
- [scifact_raw_compiled_slice.json](../../artifacts/dev/public_datasets/scifact_raw_compiled_slice.json)
- [scifact_raw_compiled_report.json](../../artifacts/dev/public_datasets/scifact_raw_compiled_report.json)
- [hotpotqa_raw_compiled_slice.json](../../artifacts/dev/public_datasets/hotpotqa_raw_compiled_slice.json)
- [hotpotqa_raw_compiled_report.json](../../artifacts/dev/public_datasets/hotpotqa_raw_compiled_report.json)
- [locomo_raw_compiled_slice.json](../../artifacts/dev/public_datasets/locomo_raw_compiled_slice.json)
- [locomo_raw_compiled_report.json](../../artifacts/dev/public_datasets/locomo_raw_compiled_report.json)

---

## 1. 这份报告回答什么

这份报告不是新的 phase gate。

它回答三个更实际的问题：

1. 当前 public-dataset validation 能不能从正式 CLI 入口稳定跑通。
2. 当前 local slice 上的检索、workspace、long-horizon 指标大致处在什么水平。
3. 后续迭代时应该用什么命令和什么阈值做阶段验收。

换句话说，这是一份 **public-dataset 首轮验收基线 + 实践说明**。

## 2. 正式验收入口

当前支持的正式入口是：

- `uv run mindtest report public-dataset ...`

不建议把 `python -m mind.cli ...` 当成验收入口。

原因不是 public-dataset 功能本身失败，而是当前 CLI 模块的加载路径还会触发现有循环导入；`mindtest` 作为 [pyproject.toml](../../pyproject.toml) 中声明的 console script 才是当前稳定口径。

本次实际验收命令：

```bash
uv run mindtest report public-dataset locomo --source tests/data/public_datasets/locomo_local_slice.json --output artifacts/dev/public_datasets/locomo_report.json
uv run mindtest report public-dataset hotpotqa --source tests/data/public_datasets/hotpotqa_local_slice.json --output artifacts/dev/public_datasets/hotpotqa_report.json
uv run mindtest report public-dataset scifact --source tests/data/public_datasets/scifact_local_slice.json --output artifacts/dev/public_datasets/scifact_report.json
```

当前也已经具备第一条 raw-import 验收路径：

```bash
uv run python scripts/compile_public_dataset_slice.py scifact --source tests/data/public_datasets/raw/scifact --output artifacts/dev/public_datasets/scifact_raw_compiled_slice.json --claim-id 101 --claim-id 102
uv run mindtest report public-dataset scifact --source artifacts/dev/public_datasets/scifact_raw_compiled_slice.json --output artifacts/dev/public_datasets/scifact_raw_compiled_report.json
uv run python scripts/compile_public_dataset_slice.py hotpotqa --source tests/data/public_datasets/raw/hotpotqa/dev_sample.json --output artifacts/dev/public_datasets/hotpotqa_raw_compiled_slice.json --example-id 5a8b57f25542995d1e6f1371 --example-id 5a7a06935542990198eaf050
uv run mindtest report public-dataset hotpotqa --source artifacts/dev/public_datasets/hotpotqa_raw_compiled_slice.json --output artifacts/dev/public_datasets/hotpotqa_raw_compiled_report.json
uv run python scripts/compile_public_dataset_slice.py locomo --source tests/data/public_datasets/raw/locomo/conversation_sample.json --output artifacts/dev/public_datasets/locomo_raw_compiled_slice.json --example-id passport --example-id departure
uv run mindtest report public-dataset locomo --source artifacts/dev/public_datasets/locomo_raw_compiled_slice.json --output artifacts/dev/public_datasets/locomo_raw_compiled_report.json
```

判定条件：

- 命令退出码为 `0`
- 报告 JSON 成功落盘
- `fixture_hash` 在重复运行时保持稳定
- 关键统计字段完整输出：`candidate_recall_at_20`、`workspace_answer_quality_score`、`average_pus`

## 3. 当前基线结果

| Dataset | Objects | Retrieval Cases | Answer Cases | Seq Count | Recall@20 | Workspace AQS | Workspace Gold Coverage | Avg PUS | 结论 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `locomo` | `10` | `3` | `2` | `1` | `1.0000` | `0.5889` | `1.0000` | `0.4150` | 检索稳定，长程复用方向正确，答案质量仍需提升 |
| `hotpotqa` | `8` | `2` | `2` | `1` | `1.0000` | `0.7208` | `0.5000` | `0.2900` | 检索稳定，但多跳答案质量和长程效果仍偏弱 |
| `scifact` | `8` | `3` | `2` | `1` | `1.0000` | `0.4833` | `0.8333` | `0.2900` | 检索稳定，但证据整合到答案的质量仍偏弱 |

当前统一 findings：

- 三个数据集在 local slice 上都保持 `candidate_recall_at_20 = 1.0`
- 三个数据集的 `workspace_answer_quality_score` 都未达到强答案水平
- `locomo` 的 `average_pus` 已经高于 `0.30`
- `hotpotqa` 和 `scifact` 的 `average_pus` 目前仍只有 `0.29`

## 4. 阶段验收阈值

当前建议把下面这组阈值作为 **阶段验收门槛**，而不是最终产品门槛：

| 指标 | 建议门槛 | 说明 |
| --- | --- | --- |
| `candidate_recall_at_20` | `>= 0.85` | 检索层最低可用线 |
| `workspace_answer_quality_score` | `>= 0.80` | workspace 产出的答案应进入“高质量可读”区间 |
| `average_pus` | `>= 0.30` | 长程复用至少方向正确，不能低于弱正收益 |
| `workspace_gold_fact_coverage` | `>= 0.70` | workspace 至少应保留大多数 gold facts |
| `finding` | 不出现显著退化描述 | 用作快速人工检查 |

按这组阈值，当前状态是：

- `locomo`：`Recall@20 = PASS`，`Gold Coverage = PASS`，`Avg PUS = PASS`，`AQS = FAIL`
- `hotpotqa`：`Recall@20 = PASS`，`Gold Coverage = FAIL`，`Avg PUS = FAIL`，`AQS = FAIL`
- `scifact`：`Recall@20 = PASS`，`Gold Coverage = PASS`，`Avg PUS = FAIL`，`AQS = FAIL`

## 5. 推荐验收实践

后续只要 public-dataset 相关链路有改动，建议按下面顺序验收。

### 5.1 结构回归

```bash
uv run pytest tests/test_public_dataset_adapters.py tests/test_public_dataset_loaders.py tests/test_public_dataset_evaluation.py -q --no-header
```

这一步回答的是：adapter、loader、report 结构有没有坏。

### 5.2 数据集跑数

```bash
uv run mindtest report public-dataset locomo --source tests/data/public_datasets/locomo_local_slice.json --output artifacts/dev/public_datasets/locomo_report.json
uv run mindtest report public-dataset hotpotqa --source tests/data/public_datasets/hotpotqa_local_slice.json --output artifacts/dev/public_datasets/hotpotqa_report.json
uv run mindtest report public-dataset scifact --source tests/data/public_datasets/scifact_local_slice.json --output artifacts/dev/public_datasets/scifact_report.json
```

这一步回答的是：真实 end-to-end 评估流程有没有坏，以及指标是否变差。

### 5.3 仓库级健康检查

```bash
uv run python scripts/ai_health_check.py --report-for-ai
```

这一步回答的是：public-dataset 迭代有没有把仓库其他部分带坏。

## 6. 当前剩余工作不再是框架能力

截至这份报告，计划中的基础框架工作已经完成。

并且，`raw dataset -> normalized local slice -> report` 路径已经在 `SciFact`、`HotpotQA` 和 `LoCoMo` 上跑通。

后续最合理的工作重点不再是继续扩 adapter 基础设施，而是二选一：

1. 提升 `workspace_answer_quality_score` 和 `average_pus`，让 `HotpotQA` / `SciFact` 达到当前阶段门槛。
2. 继续把 raw-import 从当前的 repo 内样例推进到更接近官方完整数据文件的批量切片流程，减少手工制作 slice 的成本。

## 7. 结论

当前 public-dataset validation 的结论不是“指标已经很好”，而是：

- **验证基础设施已经可用**
- **正式 CLI 验收路径已经可用**
- **三套 local slice 都能稳定跑通**
- **问题已经从“有没有验证能力”转移到“答案质量和长程效果够不够好”**

这说明当前阶段可以正式进入“带指标约束的迭代优化”，而不是继续停留在验证框架建设阶段。