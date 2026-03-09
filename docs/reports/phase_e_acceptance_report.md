# Phase E 验收报告

验收日期：`2026-03-09`

验收对象版本：

- `git HEAD = 8203ef4`
- 本报告对应对象为 `8203ef4` 之后、尚未提交的本地工作树（包含本轮 Phase E 离线维护与 formal gate 改动）

数据 / fixture 版本：

- `LongHorizonDev v1`
- `GoldenEpisodeSet v1`
- `PrimitiveGoldenCalls v1`
- `RetrievalBenchmark v1`
- `EpisodeAnswerBench v1`

验收对象：

- [phase_gates.md](../foundation/phase_gates.md)
- [implementation_stack.md](../foundation/implementation_stack.md)
- [long_horizon_dev.py](../../mind/fixtures/long_horizon_dev.py)
- [phase_e.py](../../mind/offline/phase_e.py)
- [audit.py](../../mind/offline/audit.py)
- [worker.py](../../mind/offline/worker.py)
- [service.py](../../mind/offline/service.py)
- [run_phase_e_gate.py](../../scripts/run_phase_e_gate.py)
- [test_phase_e_startup.py](../../tests/test_phase_e_startup.py)
- [test_phase_e_gate.py](../../tests/test_phase_e_gate.py)
- [test_offline_worker.py](../../tests/test_offline_worker.py)
- [test_postgres_regression.py](../../tests/test_postgres_regression.py)

相关文档：

- Phase E 启动与收敛轨迹见 [../design/phase_e_startup_checklist.md](../design/phase_e_startup_checklist.md)
- Phase E 独立审计见 [phase_e_independent_audit.md](./phase_e_independent_audit.md)

验收范围：

- `E-1` 新派生对象 trace 完整率
- `E-2` `SchemaValidationPrecision`
- `E-3` `ReplayLift`
- `E-4` `PromotionPrecision@10`
- `E-5` 离线维护净收益

验收方法：

- 按 [phase_gates.md](../foundation/phase_gates.md) 的 `E-1 ~ E-5` 逐条核对
- 运行 `python3 -m pytest -q`
- 运行 `.venv/bin/ruff check mind tests scripts`
- 运行 `.venv/bin/mypy`
- 运行 `python3 scripts/run_phase_e_startup.py`
- 运行 `python3 scripts/run_phase_e_gate.py`
- 审阅 [phase_e.py](../../mind/offline/phase_e.py)、[audit.py](../../mind/offline/audit.py)、[worker.py](../../mind/offline/worker.py)

## 1. 结论

Phase E 本次验收结论：`PASS`

判定依据：

- `E-1 ~ E-5` 五项 MUST-PASS 指标全部通过
- `offline_jobs`、`OfflineWorker`、`OfflineMaintenanceService`、promotion policy 和 `LongHorizonDev v1` 已形成统一的 Phase E gate 闭环
- `PUS / PollutionRate` 的 offline A/B dev eval 已可跑，不再只停留在 startup checklist
- 本地全量静态检查和单元测试通过，未发现对已完成 Phase B/C/D 的回归

## 2. Gate 结果

| Gate | 阈值 | 结果 | 结论 |
| --- | --- | --- | --- |
| `E-1` | `SourceTraceCoverage = 1.00` | `1.00` | `PASS` |
| `E-2` | `SchemaValidationPrecision >= 0.85` | `1.00` | `PASS` |
| `E-3` | `ReplayLift >= 1.5` | `2.07` | `PASS` |
| `E-4` | `PromotionPrecision@10 >= 0.80` | `1.00` | `PASS` |
| `E-5` | `PUS improvement >= 0.05` 且 `PollutionRate delta <= 0.02` | `+0.14`，`0.00` | `PASS` |

补充验证：

| 验证项 | 结果 |
| --- | --- |
| `pytest -q` | `75 passed, 7 skipped` |
| `ruff check mind tests scripts` | `All checks passed!` |
| `mypy` | `Success: no issues found in 55 source files` |
| `python3 scripts/run_phase_e_startup.py` | `phase_e_startup=PASS` |
| `python3 scripts/run_phase_e_gate.py` | `phase_e_gate=PASS` |

备注：

- 本轮环境未提供 `MIND_TEST_POSTGRES_DSN / MIND_POSTGRES_DSN`，因此 PostgreSQL 集成测试入口虽已接入 [test_postgres_regression.py](../../tests/test_postgres_regression.py) 和 `mind-postgres-regression`，但未在这次验收中实际执行

## 3. 逐条核对

### `E-1` 新派生对象 trace 完整率

核对结果：

- [service.py](../../mind/offline/service.py) 通过现有 primitive 路径生成新的 `ReflectionNote` 和 `SchemaNote`
- [phase_e.py](../../mind/offline/phase_e.py) 在 gate 中实际运行 `5` 个 reflection job 和 `10` 个 promotion job
- [integrity.py](../../mind/kernel/integrity.py) 对 gate 运行后的完整 store 构建 trace audit，当前 `source_trace_coverage = 1.00`

判定：

- `E-1 = PASS`

### `E-2` `SchemaValidationPrecision`

核对结果：

- [audit.py](../../mind/offline/audit.py) 为 promotion 生成的 `SchemaNote` 执行 evidence audit
- 当前共审计 `10` 个 promotion schema，`schema_validation_precision = 1.00`
- 证据来源来自 `promotion_source_refs / evidence_refs`，并通过 token overlap 与 source object 文本做可重复的支持校验

判定：

- `E-2 = PASS`

### `E-3` `ReplayLift`

核对结果：

- [long_horizon_dev.py](../../mind/fixtures/long_horizon_dev.py) 已冻结 `LongHorizonDev v1 = 30` 条序列，每条 `5` 步
- [replay.py](../../mind/offline/replay.py) 已实现 replay target ranking 与 deterministic random decile baseline
- 当前结果：
  - `top_decile_reuse_rate = 0.40`
  - `random_decile_reuse_rate = 0.19`
  - `replay_lift = 2.07`

判定：

- `E-3 = PASS`

### `E-4` `PromotionPrecision@10`

核对结果：

- [promotion.py](../../mind/offline/promotion.py) 已定义 cross-episode、无冲突的 promotion 准入
- [audit.py](../../mind/offline/audit.py) 对 promotion schema 在后续窗口内的复用与 active 状态做审计
- 当前 `10 / 10` promotion schema 满足：
  - 未被回滚、归档或废弃
  - 在后续窗口内被复用

判定：

- `E-4 = PASS`

### `E-5` 离线维护净收益

核对结果：

- [phase_e.py](../../mind/offline/phase_e.py) 已建立 `no-offline-maintenance` 与 `offline-maintenance` 的 dev A/B eval
- 当前使用统一 `PUS`：
  - `no_maintenance_pus = 0.38`
  - `maintenance_pus = 0.52`
  - `pus_improvement = 0.14`
  - `pollution_rate_delta = 0.00`
- 改进主要来自 promotion sequence 上的压缩复用，而不是阈值放宽或污染容忍

判定：

- `E-5 = PASS`

## 4. 阻断项与剩余风险

阻断项：

- 未发现阻断 Phase E 通过的硬性问题

主要发现：

- Phase E 已不再只是“jobs table + worker skeleton”，而是具备可量化 gate 的离线维护闭环
- `LongHorizonDev v1`、`SchemaValidationPrecision`、`PromotionPrecision@10` 和 `PUS` A/B eval 已进入同一个评估器
- `mind-postgres-regression` 已预留 Phase E gate 路径，后续只需在有 DSN 的环境里实际执行

非阻断风险：

- 当前 `SchemaValidationPrecision` 和 `PromotionPrecision@10` 仍属于规则化、冻结样例驱动的 gate，不代表未来开放任务上的最终 judge 设计
- 当前 Phase E 还没有第三方独立审计；外部审计可能要求补更多 evidence audit 说明或更严格的长期序列样本
- 本轮未实际跑 PostgreSQL 集成回归，因为缺少可用 DSN

## 5. 最终结论

本次验收判定：

`Phase E = PASS`

可进入下一阶段：

- 阶段 F：评测与 Baseline 完成

下一步建议：

- 发起第三方独立审计，重点核对 `LongHorizonDev v1`、`PUS` A/B eval 和 promotion audit 的口径
- 在 Phase F 中建立 `LongHorizonEval v1`，把当前 dev gate 升级为正式 benchmark comparison
