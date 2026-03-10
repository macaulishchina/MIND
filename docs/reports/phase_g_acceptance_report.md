# Phase G 验收报告

验收日期：`2026-03-10`

验收对象版本：

- `git HEAD = 234912d`
- 本报告对应对象为 `234912d` 之后、尚未提交的本地工作树（包含本轮 Phase G strategy / cost / gate 改动）

数据 / fixture 版本：

- `LongHorizonEval v1`
- `LongHorizonDev v1`
- `EpisodeAnswerBench v1`

验收对象：

- [phase_gates.md](../foundation/phase_gates.md)
- [strategy.py](../../mind/eval/strategy.py)
- [mind_system.py](../../mind/eval/mind_system.py)
- [costing.py](../../mind/eval/costing.py)
- [phase_g.py](../../mind/eval/phase_g.py)
- [run_phase_g_cost_report.py](../../scripts/run_phase_g_cost_report.py)
- [run_phase_g_strategy_dev.py](../../scripts/run_phase_g_strategy_dev.py)
- [run_phase_g_gate.py](../../scripts/run_phase_g_gate.py)
- [test_eval_strategy.py](../../tests/test_eval_strategy.py)
- [test_eval_costing.py](../../tests/test_eval_costing.py)
- [test_phase_g_gate.py](../../tests/test_phase_g_gate.py)

相关文档：

- Phase G 启动与收敛轨迹见 [../design/phase_g_startup_checklist.md](../design/phase_g_startup_checklist.md)
- 独立审计结果见 [../reports/phase_g_independent_audit.md](../reports/phase_g_independent_audit.md)；这份报告代表本地自测后的正式验收口径

验收范围：

- `G-1` 同预算下策略收益
- `G-2` 预算偏差
- `G-3` 泛化覆盖
- `G-4` 污染控制
- `G-5` 统计稳定性

验收方法：

- 按 [phase_gates.md](../foundation/phase_gates.md) 的 `G-1 ~ G-5` 逐条核对
- 运行 `python3 -m pytest -q`
- 运行 `.venv/bin/ruff check mind tests scripts`
- 运行 `.venv/bin/mypy`
- 运行 `python3 scripts/run_phase_f_gate.py --repeat-count 3 --output /tmp/phase_f_gate.json`
- 运行 `python3 scripts/run_phase_g_cost_report.py --repeat-count 3 --output /tmp/phase_g_cost_report.json`
- 运行 `python3 scripts/run_phase_g_strategy_dev.py --run-id 1`
- 运行 `python3 scripts/run_phase_g_gate.py --repeat-count 3 --output /tmp/phase_g_gate.json`

## 1. 结论

Phase G 本次验收结论：`PASS`

判定依据：

- `G-1 ~ G-5` 五项 MUST-PASS 指标全部通过
- `fixed-rule budget baseline -> optimized_v1 -> family audit -> cost audit -> gate` 已形成统一闭环
- 本地全量静态检查和单元测试通过，未发现对已完成 Phase B/C/D/E/F 的回归

## 2. Gate 结果

| Gate | 阈值 | 结果 | 结论 |
| --- | --- | --- | --- |
| `G-1` | 同预算下 `PUS >= +0.05` | `+0.08` | `PASS` |
| `G-2` | token / storage / maintenance / total 成本偏差 `<= 5%` | `0.00 / 0.00 / 0.00 / 0.00` | `PASS` |
| `G-3` | 改进出现在 `>= 2` 个任务家族 | `cross_episode_pair=+0.08`，`episode_chain=+0.08` | `PASS` |
| `G-4` | `PollutionRate` 增幅 `<= 0.02` | `+0.00` | `PASS` |
| `G-5` | `>= 3` 次独立运行，且 `PUS` 提升 `95% CI` 下界 `> 0` | `repeat_count = 3`，CI 下界 `0.08` | `PASS` |

补充验证：

| 验证项 | 结果 |
| --- | --- |
| `pytest -q` | `90 passed, 7 skipped` |
| `ruff check mind tests scripts` | `All checks passed!` |
| `mypy` | `Success: no issues found in 84 source files` |
| `python3 scripts/run_phase_f_gate.py` | `phase_f_gate=PASS` |
| `python3 scripts/run_phase_g_gate.py` | `phase_g_gate=PASS` |

## 3. 逐条核对

### `G-1` 同预算下策略收益

核对结果：

- [strategy.py](../../mind/eval/strategy.py) 已冻结 `FixedRuleMindStrategy` 和 `OptimizedMindStrategy`
- 当前 `optimized_v1` 保持总 handle budget 不变
- gate 结果：`pus_improvement = 0.08`

判定：

- `G-1 = PASS`

### `G-2` 预算偏差

核对结果：

- [costing.py](../../mind/eval/costing.py) 已冻结 `phase_g_cost_report_v1`
- `fixed-rule` 的 budget profile 已固定为：
  - `token_cost_ratio = 0.10`
  - `storage_cost_ratio = 1.20`
  - `maintenance_cost_ratio = 1.10`
  - `total_cost_ratio = 2.40`
- `optimized_v1` 相对该 budget profile 的偏差：
  - `token_budget_bias = 0.00`
  - `storage_budget_bias = 0.00`
  - `maintenance_budget_bias = 0.00`
  - `total_budget_bias = 0.00`

判定：

- `G-2 = PASS`

### `G-3` 泛化覆盖

核对结果：

- [phase_g.py](../../mind/eval/phase_g.py) 已按 family 计算 `pus_delta`
- 当前两个任务家族均有正向改进：
  - `cross_episode_pair_pus_delta = 0.08`
  - `episode_chain_pus_delta = 0.08`

判定：

- `G-3 = PASS`

### `G-4` 污染控制

核对结果：

- `optimized_v1` 与 `fixed-rule` 的 `PollutionRate` 在当前 gate 下同为 `0.00`
- 当前 `pollution_rate_delta = 0.00`

判定：

- `G-4 = PASS`

### `G-5` 统计稳定性

核对结果：

- `repeat_count = 3`
- `pus_improvement` 的 `95% CI` 下界为 `0.08`
- 当前 runner 仍为确定性实现，因此 CI 收敛为点区间；这一点在风险章节单独说明

判定：

- `G-5 = PASS`

## 4. 阻断项与剩余风险

阻断项：

- 未发现阻断 Phase G 通过的硬性问题

主要发现：

- Phase G 已经从“固定规则策略可用”推进到“策略可被优化，且优化收益可量化”
- `phase_g_cost_report_v1`、`optimized_v1`、`phase_g_gate` 已形成可引用工件

非阻断风险：

- 当前 `optimized_v1` 仍是启发式优化策略，不是学习式策略；后续若继续扩展，需要额外验证复杂策略是否仍保持预算纪律
- 当前所有系统 runner 仍是确定性实现，`95% CI` 在本地结果中收敛为点区间；这不影响 G 阶段 gate，但会降低统计信号丰富度
- 当前 Phase G 独立审计已完成并已入库；若后续扩展到更多任务家族、更长时间跨度或非确定性评测设置，仍可能需要补充复核

## 5. 最终结论

本次验收判定：

`Phase G = PASS`

当前状态：

- 阶段级工程目标已经在本地 gate 层面完成，并已通过独立审计
- 独立审计结果见 [../reports/phase_g_independent_audit.md](../reports/phase_g_independent_audit.md)
