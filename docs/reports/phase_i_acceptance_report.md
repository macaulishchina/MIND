# Phase I 验收报告

验收日期：`2026-03-10`

验收对象版本：

- `git HEAD = 019fb20`
- 本报告对应对象为 `019fb20` 之后、尚未提交的本地工作树（包含本轮 Phase I runtime access modes、benchmark、gate 与验收文档改动）

数据 / fixture 版本：

- `AccessDepthBench v1`
- `GoldenEpisodeSet v1`
- `Phase D` retrieval seed objects

验收对象：

- [phase_gates.md](../foundation/phase_gates.md)
- [phase_i_startup_checklist.md](../design/phase_i_startup_checklist.md)
- [contracts.py](../../mind/access/contracts.py)
- [service.py](../../mind/access/service.py)
- [benchmark.py](../../mind/access/benchmark.py)
- [phase_i.py](../../mind/access/phase_i.py)
- [access_depth_bench.py](../../mind/fixtures/access_depth_bench.py)
- [run_phase_i_gate.py](../../scripts/run_phase_i_gate.py)
- [test_access_contracts.py](../../tests/test_access_contracts.py)
- [test_access_service.py](../../tests/test_access_service.py)
- [test_access_benchmark.py](../../tests/test_access_benchmark.py)
- [test_phase_i_gate.py](../../tests/test_phase_i_gate.py)

相关文档：

- Phase I 启动与范围控制见 [../design/phase_i_startup_checklist.md](../design/phase_i_startup_checklist.md)
- Phase I gate 与阶段定义见 [../foundation/phase_gates.md](../foundation/phase_gates.md)

验收范围：

- `I-1` access mode 合约完整度
- `I-2` `Flash` 场景下限
- `I-3` `Recall` 场景下限
- `I-4` `Reconstruct` 场景下限
- `I-5` `Reflective` 场景下限
- `I-6` `auto` 质量 / 成本前沿
- `I-7` `auto` 切换稳定性与可解释性
- `I-8` 用户锁定档位遵从率

验收方法：

- 按 [phase_gates.md](../foundation/phase_gates.md) 的 `I-1 ~ I-8` 逐条核对
- 运行 `.venv/bin/pytest -q`
- 运行 `.venv/bin/ruff check mind tests scripts`
- 运行 `.venv/bin/mypy`
- 运行 `python3 scripts/run_phase_c_gate.py`
- 运行 `python3 scripts/run_phase_h_gate.py`
- 运行 `python3 scripts/run_phase_i_gate.py`
- 运行 `python3 scripts/run_phase_g_gate.py`

## 1. 结论

Phase I 本次验收结论：`PASS`

判定依据：

- `I-1 ~ I-8` 八项 MUST-PASS 指标全部通过
- `Flash / Recall / Reconstruct / Reflective / auto` 已形成统一合约、统一 trace、统一 benchmark 与 formal gate
- `auto` 已具备 `upgrade / downgrade / jump` 三类具名切换，并保留显式锁档遵从
- 本地静态检查、测试与相关前序 gate 复跑通过，未发现对已完成 Phase C/H/G 的回归

## 2. Gate 结果

| Gate | 阈值 | 结果 | 结论 |
| --- | --- | --- | --- |
| `I-1` | `5/5` mode 全部可调用；mode trace coverage `= 100%` | `5 / 5`，`303 / 303` | `PASS` |
| `I-2` | `Flash` / `speed-sensitive`：`TimeBudgetHitRate >= 0.95`，`ConstraintSatisfaction >= 0.95` | `1.00 / 1.00` | `PASS` |
| `I-3` | `Recall` / `balanced`：`AQS >= 0.75`，`MUS >= 0.65` | `1.00 / 0.85` | `PASS` |
| `I-4` | `Reconstruct` / `high-correctness`：`AnswerFaithfulness >= 0.95`，`GoldFactCoverage >= 0.90` | `0.99 / 0.96` | `PASS` |
| `I-5` | `Reflective` / `high-correctness`：`AnswerFaithfulness >= 0.97`，`GoldFactCoverage >= 0.92`，`ConstraintSatisfaction >= 0.98` | `0.99 / 0.96 / 1.00` | `PASS` |
| `I-6` | `auto`：平均 `AQS` 降幅 `<= 0.02`，且 `CostEfficiencyScore` 不低于 family-best fixed mode | `0.0000`，cost regression `0` | `PASS` |
| `I-7` | `upgrade / downgrade / jump` 都至少有具名 trace；无原因码切换 `= 0`；震荡率 `<= 5%` | `1 / 1 / 21`，missing reason `0`，oscillation `0 / 63` | `PASS` |
| `I-8` | 显式固定 `Flash / Recall / Reconstruct / Reflective` 时被 `auto` 覆盖比例 `= 0` | `0 / 240` | `PASS` |

补充验证：

| 验证项 | 结果 |
| --- | --- |
| `.venv/bin/pytest -q` | `174 passed, 11 skipped` |
| `.venv/bin/ruff check mind tests scripts` | `All checks passed!` |
| `.venv/bin/mypy` | `Success: no issues found in 109 source files` |
| `python3 scripts/run_phase_c_gate.py` | `phase_c_gate=PASS` |
| `python3 scripts/run_phase_h_gate.py` | `phase_h_gate=PASS` |
| `python3 scripts/run_phase_i_gate.py` | `phase_i_gate=PASS` |
| `python3 scripts/run_phase_g_gate.py` | `phase_g_gate=PASS` |

## 3. 逐条核对

### `I-1` access mode 合约完整度

核对结果：

- [contracts.py](../../mind/access/contracts.py) 已冻结 `Flash / Recall / Reconstruct / Reflective / auto` 的请求、响应与 trace contract
- [service.py](../../mind/access/service.py) 的运行轨迹统一以 `select_mode -> ... -> mode_summary` 收口
- [phase_i.py](../../mind/access/phase_i.py) gate 场景下，`5 / 5` 档位都完成真实调用，trace coverage 为 `303 / 303`

判定：

- `I-1 = PASS`

### `I-2` `Flash` 场景下限

核对结果：

- [benchmark.py](../../mind/access/benchmark.py) 已将 `speed-sensitive` 任务族固定纳入 `AccessDepthBench v1`
- 当前 `Flash` / `speed-sensitive` 聚合结果：
  - `TimeBudgetHitRate = 1.00`
  - `ConstraintSatisfaction = 1.00`

判定：

- `I-2 = PASS`

### `I-3` `Recall` 场景下限

核对结果：

- `Recall` 作为默认平衡档，当前 `balanced` 聚合结果：
  - `AQS = 1.00`
  - `MUS = 0.85`

判定：

- `I-3 = PASS`

### `I-4` `Reconstruct` 场景下限

核对结果：

- [service.py](../../mind/access/service.py) 的 `Reconstruct` 已支持 `source_refs` 扩展读取与 workspace 重建
- 当前 `high-correctness` 聚合结果：
  - `AnswerFaithfulness = 0.9875`
  - `GoldFactCoverage = 0.9625`

判定：

- `I-4 = PASS`

### `I-5` `Reflective` 场景下限

核对结果：

- [service.py](../../mind/access/service.py) 的 `Reflective` 在 `Reconstruct` 基础上增加 verification notes
- 当前 `high-correctness` 聚合结果：
  - `AnswerFaithfulness = 0.9875`
  - `GoldFactCoverage = 0.9625`
  - `ConstraintSatisfaction = 1.0000`

判定：

- `I-5 = PASS`

### `I-6` `auto` 质量 / 成本前沿

核对结果：

- [benchmark.py](../../mind/access/benchmark.py) 已对 `flash / recall / reconstruct / reflective_access / auto` 全量运行 `AccessDepthBench v1`
- [phase_i.py](../../mind/access/phase_i.py) 会按任务族比较 `auto` 与 family-best fixed mode
- 当前结果：
  - `auto_frontier_average_aqs_drop = 0.0000`
  - `auto_frontier_cost_regression_count = 0`

判定：

- `I-6 = PASS`

### `I-7` `auto` 切换稳定性与可解释性

核对结果：

- [service.py](../../mind/access/service.py) 当前支持：
  - `upgrade`
  - `downgrade`
  - `jump`
- [phase_i.py](../../mind/access/phase_i.py) 会把 `AccessDepthBench v1` 的 `auto` 运行与三个具名 targeted scenario 一起纳入审计
- 当前审计结果：
  - `upgrade = 1`
  - `downgrade = 1`
  - `jump = 21`
  - 无原因码切换 `= 0`
  - 震荡 `= 0 / 63`

判定：

- `I-7 = PASS`

### `I-8` 用户锁定档位遵从率

核对结果：

- [contracts.py](../../mind/access/contracts.py) 已强制显式固定档位不得被覆盖
- [phase_i.py](../../mind/access/phase_i.py) 当前对 `60 case x 4 fixed mode = 240` 条显式锁档请求做了回归核对
- 当前 `fixed_lock_override_count = 0 / 240`

判定：

- `I-8 = PASS`

## 4. 阻断项与剩余风险

阻断项：

- 未发现阻断 Phase I 通过的硬性问题

主要发现：

- runtime access depth 现在已经不是抽象命名，而是可执行、可比较、可调参的运行时策略层
- `auto` 调度仍然保持轻量，没有越权改写用户显式固定档位，也没有把 provenance 混进 retrieval / ranking

非阻断风险：

- 当前 `auto` audit 的 `upgrade / downgrade` 仍然依赖具名 targeted scenario；后续如果 benchmark 分布变化，最好把这三类切换逐步沉入更大的公共评测集
- `Reflective` 当前仍然是 runtime verification 强化，不等同于后续人格层或治理层的更重反思机制
- Phase I 没有新增存储 schema；因此这次验收没有引入新的 PostgreSQL 专项 gate，后续如果 runtime access 开始依赖新的持久化结构，需要补 PG 定向回归

## 5. 最终结论

本次验收判定：

`Phase I = PASS`

当前状态：

- Phase I 已具备本地 formal gate，默认工件输出为 [artifacts/phase_i/gate_report.json](../../artifacts/phase_i/gate_report.json)
- 下一阶段可进入 `Phase J: Unified CLI Experience`
