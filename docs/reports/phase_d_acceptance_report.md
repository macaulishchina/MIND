# Phase D 验收报告

验收日期：`2026-03-09`

验收对象：

- [phase_gates.md](../foundation/phase_gates.md)
- [implementation_stack.md](../foundation/implementation_stack.md)
- [retrieval_benchmark.py](../../mind/fixtures/retrieval_benchmark.py)
- [episode_answer_bench.py](../../mind/fixtures/episode_answer_bench.py)
- [phase_d.py](../../mind/workspace/phase_d.py)
- [answer_benchmark.py](../../mind/workspace/answer_benchmark.py)
- [context_protocol.py](../../mind/workspace/context_protocol.py)
- [run_phase_d_smoke.py](../../scripts/run_phase_d_smoke.py)
- [test_phase_d_smoke.py](../../tests/test_phase_d_smoke.py)
- [test_postgres_regression.py](../../tests/test_postgres_regression.py)

相关文档：

- Phase D 当前状态与 pre-acceptance smoke 记录见 [phase_d_smoke_report.md](./phase_d_smoke_report.md)
- Phase D 独立审计见 [phase_d_independent_audit.md](./phase_d_independent_audit.md)

验收范围：

- `D-1` 检索模式覆盖
- `D-2` Candidate recall@20
- `D-3` Workspace gold-fact coverage
- `D-4` Workspace 槽位纪律
- `D-5` 相对 `raw-top20 baseline` 的成本收益门槛

验收方法：

- 按 [phase_gates.md](../foundation/phase_gates.md) 的 `D-1 ~ D-5` 逐条核对
- 运行 `python3 -m pytest -q`
- 运行 `.venv/bin/ruff check mind tests scripts`
- 运行 `.venv/bin/mypy`
- 运行 `python3 scripts/run_phase_d_smoke.py`
- 运行 `MIND_POSTGRES_DSN=... .venv/bin/mind-postgres-regression`
- 审阅 [postgres_store.py](../../mind/kernel/postgres_store.py)、[retrieval.py](../../mind/kernel/retrieval.py)、[builder.py](../../mind/workspace/builder.py)、[answer_benchmark.py](../../mind/workspace/answer_benchmark.py)

## 1. 结论

Phase D 本次验收结论：`PASS`

判定依据：

- `D-1 ~ D-5` 五项 MUST-PASS 指标全部通过
- `pg_trgm / pgvector / object_embeddings` 已进入正式 PostgreSQL 检索路径
- `EpisodeAnswerBench v1` 已建立，`D-5` 已从 proxy baseline 升级为 answer-level A/B benchmark
- SQLite smoke 与 PostgreSQL regression 两条路径均通过，未发现对 Phase B/C gate 的回归

## 2. Gate 结果

| Gate | 阈值 | 结果 | 结论 |
| --- | --- | --- | --- |
| `D-1` | `3/3` 模式可用：`keyword / vector / time-window` | `4 / 4 / 4` smoke successes | `PASS` |
| `D-2` | `Candidate recall@20 >= 0.85` | `1.00` | `PASS` |
| `D-3` | `Workspace gold-fact coverage >= 0.80` | `1.00` | `PASS` |
| `D-4` | `slot_count <= K` 且 `100% slot has source refs` | `1.00 / 1.00` | `PASS` |
| `D-5` | `median token cost <= 0.60x` 且 `task success drop <= 5pp` | `0.18x`，`0.00pp` | `PASS` |

补充验证：

| 验证项 | 结果 |
| --- | --- |
| `pytest -q` | `32 passed, 5 skipped` |
| `ruff check mind tests scripts` | `All checks passed!` |
| `mypy` | `Success: no issues found in 40 source files` |
| `python3 scripts/run_phase_d_smoke.py` | `phase_d_smoke=PASS` |
| `mind-postgres-regression` | `phase_b_gate=PASS`，`phase_c_gate=PASS`，`phase_d_smoke=PASS` |

## 3. 逐条核对

### `D-1` 检索模式覆盖

核对结果：

- [service.py](../../mind/primitives/service.py) 已通过 store-level retrieval contract 统一接入 `keyword / vector / time-window`
- [postgres_store.py](../../mind/kernel/postgres_store.py) 已实现 PostgreSQL 原生 keyword / vector / time-window 检索
- [test_phase_d_smoke.py](../../tests/test_phase_d_smoke.py) 与 [test_postgres_regression.py](../../tests/test_postgres_regression.py) 验证 `3/3` 模式均可用

判定：

- `D-1 = PASS`

### `D-2` Candidate recall@20

核对结果：

- [retrieval_benchmark.py](../../mind/fixtures/retrieval_benchmark.py) 已冻结 `RetrievalBenchmark v1 = 100` 个 benchmark case
- [phase_d.py](../../mind/workspace/phase_d.py) 对全部 `100` 个 case 计算 `candidate_recall_at_20`
- 当前结果为 `1.00`

判定：

- `D-2 = PASS`

### `D-3` Workspace gold-fact coverage

核对结果：

- [builder.py](../../mind/workspace/builder.py) 已将 `slot_limit / source_refs / expand_pointer` 收敛为可执行约束
- [phase_d.py](../../mind/workspace/phase_d.py) 对 `100` 个 benchmark case 计算 workspace gold-fact coverage
- 当前结果为 `1.00`

判定：

- `D-3 = PASS`

### `D-4` Workspace 槽位纪律

核对结果：

- [builder.py](../../mind/workspace/builder.py) 统一执行 candidate 去重、优先级排序和 slot 构建
- [test_workspace_builder.py](../../tests/test_workspace_builder.py) 与 [test_phase_d_smoke.py](../../tests/test_phase_d_smoke.py) 验证 `slot_count <= K` 和 `source_refs` 完整性
- 当前结果为 `workspace_slot_discipline = 1.00`，`workspace_source_ref_coverage = 1.00`

判定：

- `D-4 = PASS`

### `D-5` 成本收益门槛

核对结果：

- [context_protocol.py](../../mind/workspace/context_protocol.py) 已冻结 `raw-top20 / workspace` 上下文序列化与 token 计量协议
- [episode_answer_bench.py](../../mind/fixtures/episode_answer_bench.py) 已建立 `EpisodeAnswerBench v1 = 100` 个单回答样例
- [answer_benchmark.py](../../mind/workspace/answer_benchmark.py) 已实现 answer-level A/B runner 与规则评分
- [phase_d.py](../../mind/workspace/phase_d.py) 现在对 `raw-top20` 与 `workspace` 同时计算：
  - `task_success_rate`
  - `task_success_drop_pp`
  - `answer_quality_score`
  - `median_token_cost_ratio`
- 当前结果为：
  - `median_token_cost_ratio = 0.18`
  - `raw_top20_task_success = 1.00`
  - `workspace_task_success = 1.00`
  - `task_success_drop_pp = 0.00`

判定：

- `D-5 = PASS`

## 4. 阻断项与剩余风险

阻断项：

- 未发现阻断 Phase D 通过的硬性问题

主要发现：

- `PostgreSQL` 已成为 Phase D 的正式主存储路径；`SQLite` 继续保留为 reference/test backend
- answer-level `D-5` 已落地，不再依赖 `task_success_proxy`
- `mind-postgres-regression` 现在能同时回归 Phase B / C / D，而不是只测存储骨架

非阻断风险：

- 当前 `EpisodeAnswerBench v1` 仍是规则化、冻结样例驱动的 answer bench，不代表后续开放任务上的最终 judge 设计
- 当前 `pgvector` 路径使用本地 deterministic embedding 作为正式 Phase D 基线；更高质量的 provider embedding 属于后续优化项
- Phase D 的独立审计尚未执行，外部审计可能会要求补充更细的 evidence audit 或 benchmark 说明

## 5. 最终结论

本次验收判定：

`Phase D = PASS`

可进入下一阶段：

- 阶段 E：反思、离线维护与轻量重组

下一步建议：

- 发起第三方独立审计，核对 `EpisodeAnswerBench v1`、PostgreSQL retrieval path 和 `D-5` 评分脚本
- 在 Phase E 中优先把 replay / reflect / promotion 的 traceability 与长期收益指标接入同一套 benchmark 体系
