# Phase D Smoke Baseline + D-5 Raw-Top20 Benchmark — 当前状态报告

时点说明：本报告记录的是 Phase D 从“检索 / workspace 基线闭环”推进到“`D-5` 可跑”这一 pre-acceptance 时点的状态。后续 `pg_trgm / pgvector / object_embeddings` 正式接入、`EpisodeAnswerBench v1` 建立完成、answer-level `D-5` 通过后的最新正式结论，见 [phase_d_acceptance_report.md](./phase_d_acceptance_report.md)。

| 项目 | 值 |
| --- | --- |
| 评估范围 | Retrieval v1、Workspace builder v1、`RetrievalBenchmark v0 / v1`、Phase D smoke、D-5 raw-top20 baseline |
| 评估日期 | 2026-03-09 |
| 评估对象 | 当前本地工作树（未提交的 Phase D 改动） |
| 评估方式 | 代码审读 + 自动化检查（ruff / mypy / pytest / Phase D smoke / PostgreSQL regression） |

---

## 1. 这份报告回答什么

这份报告不宣称 `Phase D = PASS`。

它只回答两个问题：

1. Phase D 当前已经落地了哪些可执行能力。
2. `D-5` 是否已经从文档占位项推进为一个可跑的 benchmark。

换句话说，这是一份 **当前状态报告**，不是正式验收报告。

---

## 2. 当前已落地内容

本地工作树当前已经具备：

- PostgreSQL 正式 backend、Alembic 初版迁移和 Phase B/C/D PostgreSQL regression
- Retrieval v1：最新版本选择与基础 filters 下推到 store / SQL 层
- Workspace builder v1：`slot_limit`、`source_refs`、slot traceability 变成可执行约束
- `RetrievalBenchmark v0`：固定 `12` 个 smoke case，覆盖 `keyword / vector / time-window`
- `RetrievalBenchmark v1`：固定 `100` 个 benchmark case，用于 `D-2 / D-3 / D-5`
- Phase D smoke evaluator：`v0` 负责 `D-1`，`v1` 负责 benchmark 指标
- 冻结的 `raw-top20 / workspace` context protocol：明确上下文序列化与 token 计量口径
- `D-5 raw-top20 baseline`：覆盖 token cost 与 task success proxy 的 A/B 对照

其中 `D-5` 当前的 system / baseline 定义为：

- system：`retrieve -> workspace builder -> structured workspace context`
- baseline：`retrieve -> raw top-20 object context`

当前计算的 `D-5` 指标为：

- `median_token_cost_ratio`
- `task_success_proxy_drop_pp`

这里的 `task success proxy` 目前定义为：

`workspace 或 raw-top20 对 gold facts 的覆盖是否达到 100%`

这是一种 **确定性代理指标**，不是最终的 answer-level task completion benchmark。

---

## 3. 自动化结果

### 3.1 基础检查

| 检查项 | 结果 |
| --- | --- |
| `ruff check mind tests scripts` | **PASS** |
| `mypy` | **PASS**（`34 source files`） |
| `python3 -m pytest -q` | **PASS**（`27 passed, 4 skipped`） |

### 3.2 Phase D smoke（SQLite）

`python3 scripts/run_phase_d_smoke.py`

结果：

- `retrieval_smoke_cases=12`
- `retrieval_benchmark_cases=100`
- `keyword / time_window / vector = 4 / 4 / 4`
- `candidate_recall_at_20 = 1.00`
- `workspace_gold_fact_coverage = 1.00`
- `workspace_slot_discipline = 1.00`
- `workspace_source_ref_coverage = 1.00`
- `median_token_cost_ratio = 0.35`
- `raw_top20_task_success_proxy = 1.00`
- `workspace_task_success_proxy = 1.00`
- `task_success_proxy_drop_pp = 0.00`
- `D-1 ~ D-5 = PASS`

### 3.3 PostgreSQL regression

`MIND_POSTGRES_DSN=... .venv/bin/mind-postgres-regression`

结果：

- `phase_b_gate = PASS`
- `phase_c_gate = PASS`
- `phase_d_smoke = PASS`
- `phase_d_recall_at_20 = 1.00`
- `phase_d_workspace_coverage = 1.00`
- `phase_d_workspace_discipline = 1.00`
- `phase_d_token_cost_ratio = 0.35`
- `phase_d_task_success_proxy_drop_pp = 0.00`

---

## 4. 当前结论

当前可以确认：

1. Phase D 已经不再停留在“只有 store 和 builder 骨架”的状态。
2. Retrieval / Workspace / raw-top20 baseline 已形成最小可回归闭环。
3. `RetrievalBenchmark v1` 已建立，`D-2 / D-3` 已经不再依赖说明性小样例。
4. `D-5` 已经从 gate 表格中的占位项，推进成实际可跑的 benchmark。

当前不能宣称：

1. `Phase D = PASS`
2. `D-5` 已使用正式 answer-level benchmark 完成验收

原因很明确：

- 当前 `D-5` 的 success 指标仍是 `task_success_proxy`，不是基于 `EpisodeAnswerBench` 或冻结 answer rubric 的正式 `TaskCompletionScore`。
- 当前虽然已有 `RetrievalBenchmark v1` 和自动化结果，但还缺少正式的 answer-level A/B benchmark、独立审计和具名 Phase D 验收记录。

因此，最准确的状态表述应为：

`Phase D smoke baseline = PASS`

而不是：

`Phase D 正式验收 = PASS`

---

## 5. 剩余工作

要把当前状态推进到正式的 Phase D gate，下一步至少还需要：

1. 将 `D-5` 从 `task_success_proxy` 升级为正式 answer-level A/B benchmark。
2. 将当前 benchmark 结果沉淀为正式可引用版本，并补 Phase D 独立审计。
3. 在审计通过后产出正式 Phase D 验收记录。

---

## 6. 一句话结论

Phase D 当前已经具备可运行的 Retrieval / Workspace / raw-top20 baseline 闭环；`D-5` 现在是 **可跑的 benchmark**，但仍属于 **正式验收前的 proxy baseline**，不能代替完整的 Phase D gate。
