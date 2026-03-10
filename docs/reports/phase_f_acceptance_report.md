# Phase F 验收报告

验收日期：`2026-03-09`

验收对象版本：

- `git HEAD = 54f1eb9`
- 本报告对应对象为 `54f1eb9` 之后、尚未提交的本地工作树（包含本轮 Phase F benchmark / comparison / ablation 改动）

数据 / fixture 版本：

- `LongHorizonEval v1`
- `LongHorizonDev v1`
- `GoldenEpisodeSet v1`
- `EpisodeAnswerBench v1`

验收对象：

- [phase_gates.md](../foundation/phase_gates.md)
- [long_horizon_eval.py](../../mind/fixtures/long_horizon_eval.py)
- [runner.py](../../mind/eval/runner.py)
- [baselines.py](../../mind/eval/baselines.py)
- [reporting.py](../../mind/eval/reporting.py)
- [mind_system.py](../../mind/eval/mind_system.py)
- [phase_f.py](../../mind/eval/phase_f.py)
- [run_phase_f_gate.py](../../scripts/run_phase_f_gate.py)
- [test_phase_f_gate.py](../../tests/test_phase_f_gate.py)
- [test_phase_f_comparison.py](../../tests/test_phase_f_comparison.py)

相关文档：

- Phase F 启动与收敛轨迹见 [../design/phase_f_startup_checklist.md](../design/phase_f_startup_checklist.md)
- Phase F 独立审核报告见 [phase_f_independent_audit.md](phase_f_independent_audit.md)

验收范围：

- `F-1` 评测集冻结
- `F-2` baseline 完整性
- `F-3` 统计报告完整性
- `F-4` 相对 `no-memory` 优势
- `F-5` 相对 `fixed summary memory` 优势
- `F-6` 相对 `plain RAG` 非劣
- `F-7` `workspace / offline maintenance` ablation

验收方法：

- 按 [phase_gates.md](../foundation/phase_gates.md) 的 `F-1 ~ F-7` 逐条核对
- 运行 `python3 -m pytest -q`
- 运行 `.venv/bin/ruff check mind tests scripts`
- 运行 `.venv/bin/mypy`
- 运行 `python3 scripts/run_phase_f_manifest.py`
- 运行 `python3 scripts/run_phase_f_report.py --repeat-count 3 --output /tmp/phase_f_report.json`
- 运行 `python3 scripts/run_phase_f_comparison.py --repeat-count 3 --output /tmp/phase_f_comparison.json`
- 运行 `python3 scripts/run_phase_f_gate.py --repeat-count 3 --output /tmp/phase_f_gate.json`

## 1. 结论

Phase F 本次验收结论：`PASS`

判定依据：

- `F-1 ~ F-7` 七项 MUST-PASS 指标全部通过
- `LongHorizonEval v1`、3 个 baseline、`95% CI` report、`F-4 ~ F-6` comparison 和 `F-7` ablation 已形成统一 gate 闭环
- 本地全量静态检查和单元测试通过，未发现对已完成 Phase B/C/D/E 的回归

## 2. Gate 结果

| Gate | 阈值 | 结果 | 结论 |
| --- | --- | --- | --- |
| `F-1` | `LongHorizonEval v1` 已冻结，`>= 50` 条，`5~10` 步 | `50` 条，`6..6` 步 | `PASS` |
| `F-2` | `3/3` baseline 可运行 | `no-memory / plain RAG / fixed summary memory` 全可运行 | `PASS` |
| `F-3` | 每个系统 `>= 3` 次独立运行，并给出 `95% CI` | `repeat_count = 3`，CI report 已落盘 | `PASS` |
| `F-4` | 相对 `no-memory`，`PUS >= +0.10` 且 CI 下界 `> 0` | `+0.45`，CI 下界 `0.45` | `PASS` |
| `F-5` | 相对 `fixed summary memory`，`PUS >= +0.05` 且 CI 下界 `> 0` | `+0.17`，CI 下界 `0.17` | `PASS` |
| `F-6` | 相对 `plain RAG`，`PUS >= -0.02` | `+0.26` | `PASS` |
| `F-7` | 去掉 `workspace` 或 `offline maintenance` 时，`PUS` 下降 `>= 0.03` | `workspace=+0.07`，`offline maintenance=+0.06` | `PASS` |

补充验证：

| 验证项 | 结果 |
| --- | --- |
| `pytest -q` | `84 passed, 7 skipped` |
| `ruff check mind tests scripts` | `All checks passed!` |
| `mypy` | `Success: no issues found in 75 source files` |
| `python3 scripts/run_phase_f_gate.py` | `phase_f_gate=PASS` |

## 3. 逐条核对

### `F-1` 评测集冻结

核对结果：

- [long_horizon_eval.py](../../mind/fixtures/long_horizon_eval.py) 已冻结 `LongHorizonEval v1 = 50` 条序列
- manifest hash 固定为 `24f203c01bae3cad01fe741a8244b1c1224413579433d22131935ad723740a49`
- [run_phase_f_manifest.py](../../scripts/run_phase_f_manifest.py) 可直接输出版本化 manifest

判定：

- `F-1 = PASS`

### `F-2` baseline 完整性

核对结果：

- [baselines.py](../../mind/eval/baselines.py) 已落地 `no-memory / plain RAG / fixed summary memory`
- [run_phase_f_baselines.py](../../scripts/run_phase_f_baselines.py) 能直接运行三者
- 当前基线均能完成完整 `LongHorizonEval v1` run

判定：

- `F-2 = PASS`

### `F-3` 统计报告完整性

核对结果：

- [reporting.py](../../mind/eval/reporting.py) 已冻结 `phase_f_benchmark_report_v1`
- [run_phase_f_report.py](../../scripts/run_phase_f_report.py) 已支持 `repeat_count >= 3`
- 当前 report 已包含 system-level raw values、mean 和 `95% CI`

判定：

- `F-3 = PASS`

### `F-4 ~ F-6` benchmark comparison

核对结果：

- [mind_system.py](../../mind/eval/mind_system.py) 已落地当前 MIND runner
- [phase_f.py](../../mind/eval/phase_f.py) 已统一计算：
  - `mind vs no-memory`
  - `mind vs fixed summary memory`
  - `mind vs plain RAG`
- 当前比较结果：
  - `mind_pus_mean = 0.40`
  - `mind_vs_no_memory_diff = 0.45`
  - `mind_vs_fixed_summary_memory_diff = 0.17`
  - `mind_vs_plain_rag_diff = 0.26`

判定：

- `F-4 = PASS`
- `F-5 = PASS`
- `F-6 = PASS`

### `F-7` 关键组件可归因

核对结果：

- [mind_system.py](../../mind/eval/mind_system.py) 已支持 `use_workspace=False` 和 `use_offline_maintenance=False` 的显式 ablation
- [phase_f.py](../../mind/eval/phase_f.py) 已把这两条 ablation 接入同一 gate
- 当前 gate 结果：
  - `workspace_ablation_drop = 0.07`
  - `offline_maintenance_ablation_drop = 0.06`
- gate 已验证：去掉任一组件时，`PUS` 均下降至少 `0.03`

判定：

- `F-7 = PASS`

## 4. 阻断项与剩余风险

阻断项：

- 未发现阻断 Phase F 通过的硬性问题

主要发现：

- Phase F 已不再只是“有 benchmark 工具链”，而是形成了 `manifest -> baselines -> CI report -> comparison -> ablation -> gate` 的完整闭环
- `LongHorizonEval v1`、`phase_f_benchmark_report_v1` 和 `phase_f_gate` 已形成可引用工件

非阻断风险：

- 当前所有系统 runner 仍是确定性实现，`95% CI` 在本地结果中收敛为点区间；这不影响 F 阶段 gate，但会降低统计信号丰富度
- 当前 Phase F 还没有第三方独立审计；外部审计可能会要求更严格的长期样本、更多任务家族或更真实的随机性来源

## 5. 最终结论

本次验收判定：

`Phase F = PASS`

可进入下一阶段：

- 阶段 G：策略优化完成

下一步建议：

- 发起第三方独立审计，重点核对 `LongHorizonEval v1`、comparison / ablation 口径和 `MindLongHorizonSystem` 的合理性
- 进入 Phase G，开始“优化策略相对固定规则策略”的同预算收益验证
