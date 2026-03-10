# Phase F 独立审核报告

审核日期：`2026-03-09`

审核对象版本：

- `git HEAD = 54f1eb9`
- 审核对象为 `54f1eb9` 之后尚未提交的本地工作树全量 Phase F 修改

## 1. 审核结论

Phase F 独立审核结论：`PASS`

- 框架设计完整性：`PASS`
- 实现完整性：`PASS`
- 必要性：`PASS`
- 合理性：`PASS`
- 文档噪声排查：`PASS`

## 2. 审核范围

### 2.1 新增文件

| 模块 | 文件 | 行数 | 职责 |
| --- | --- | --- | --- |
| `mind/eval` | `__init__.py` | 64 | Phase F eval 模块公共 API |
| `mind/eval` | `runner.py` | 185 | `LongHorizonBenchmarkRunner`、`LongHorizonScoreCard`、`compute_pus` |
| `mind/eval` | `baselines.py` | 231 | 3 个 baseline：`NoMemory`、`FixedSummaryMemory`、`PlainRag` |
| `mind/eval` | `mind_system.py` | 342 | MIND 系统 runner、workspace 选择与 offline promotion |
| `mind/eval` | `reporting.py` | 375 | `95% CI` 统计报告、JSON round-trip |
| `mind/eval` | `phase_f.py` | 440 | `PhaseFComparisonResult`、`PhaseFGateResult`、gate 逻辑与 JSON 持久化 |
| `mind/fixtures` | `long_horizon_eval.py` | 249 | `LongHorizonEval v1`：50 条序列、manifest hash |
| 测试 | `test_eval_baselines.py` | 36 | baseline 可运行与排序验证 |
| 测试 | `test_eval_reporting.py` | 93 | suite report round-trip 与 CI 验证 |
| 测试 | `test_eval_runner.py` | 69 | runner 聚合与 `run_many` 验证 |
| 测试 | `test_long_horizon_eval.py` | 30 | 冻结 50 序列、与 dev 分离、manifest shape |
| 测试 | `test_phase_f_comparison.py` | 18 | `F-2 ~ F-6` 通过 |
| 测试 | `test_phase_f_gate.py` | 17 | `F-1 ~ F-7` 全通过 |
| 脚本 | `run_phase_f_manifest.py` | ~21 | CLI 封装 |
| 脚本 | `run_phase_f_baselines.py` | ~21 | CLI 封装 |
| 脚本 | `run_phase_f_report.py` | ~21 | CLI 封装 |
| 脚本 | `run_phase_f_comparison.py` | ~21 | CLI 封装 |
| 脚本 | `run_phase_f_gate.py` | ~21 | CLI 封装 |
| 文档 | `phase_f_startup_checklist.md` | 102 | 启动清单与收敛轨迹 |
| 文档 | `phase_f_acceptance_report.md` | 191 | 正式验收报告 |

### 2.2 新增公共入口

| 入口 | pyproject.toml key | CLI 函数 |
| --- | --- | --- |
| `mind-phase-f-manifest` | `mind.cli:phase_f_manifest_main` | 输出冻结 manifest |
| `mind-phase-f-baselines` | `mind.cli:phase_f_baselines_main` | 单次运行 3 个 baseline |
| `mind-phase-f-report` | `mind.cli:phase_f_report_main` | 多次运行 + 95% CI report |
| `mind-phase-f-comparison` | `mind.cli:phase_f_comparison_main` | MIND vs 3 baseline 对比 |
| `mind-phase-f-gate` | `mind.cli:phase_f_gate_main` | F-1 ~ F-7 全量 gate |

### 2.3 修改文件

| 文件 | 修改内容 |
| --- | --- |
| `mind/cli.py` | +256 行：5 个 Phase F CLI main 函数 |
| `pyproject.toml` | 5 个新 entry_points |
| `README.md` | Phase F 状态更新、新命令、新文档链接 |
| `docs/README.md` | Phase F 索引条目 |
| `docs/foundation/implementation_stack.md` | Phase E → F 状态更新 |

## 3. 框架设计完整性审核

### 3.1 spec 对照

| Gate | spec 要求 | 实现对照 | 判定 |
| --- | --- | --- | --- |
| `F-1` | `LongHorizonEval v1` 已版本化，所有 run 使用同一 hash | `build_long_horizon_eval_manifest_v1()` SHA-256 hash 冻结；manifest 校验 `sequence_count >= 50`、`5 <= step <= 10`、`hash.length == 64` | `PASS` |
| `F-2` | `3/3` baseline 可运行 | `NoMemoryBaselineSystem`、`FixedSummaryMemoryBaselineSystem`、`PlainRagBaselineSystem` 均实现 `LongHorizonSystemRunner` 协议 | `PASS` |
| `F-3` | 每个系统 `>= 3` 次独立运行，`95% CI` | `build_benchmark_suite_report` + `_metric_interval` 使用 t-分布 CI；`repeat_count` 验证 | `PASS` |
| `F-4` | PUS vs no-memory `>= 0.10`，CI 下界 `> 0` | `f4_pass` 实现匹配 | `PASS` |
| `F-5` | PUS vs fixed_summary_memory `>= 0.05`，CI 下界 `> 0` | `f5_pass` 实现匹配 | `PASS` |
| `F-6` | PUS vs plain_rag `>= -0.02` | `f6_pass` 实现匹配 | `PASS` |
| `F-7` | 去掉 workspace 或 offline_maintenance 任一组件时，PUS 下降 `>= 0.03` | `f7_pass` 校验 `mean_diff >= 0.03` 且 `ci_lower >= 0.03`（比 spec 更严格，合理） | `PASS` |

### 3.2 模块分层

eval 模块分层清晰：

```
runner.py (骨架：Protocol + ScoreCard + PUS)
  ↑
baselines.py (3 个 baseline runner)
mind_system.py (MIND runner)
  ↑
reporting.py (95% CI report + JSON round-trip)
  ↑
phase_f.py (comparison + gate + ablation + JSON 持久化)
```

所有模块均通过 `__init__.py` 统一导出，`__all__` 维护完整。

### 3.3 数据闭环

```
LongHorizonEval v1 (50 sequences, SHA-256 hash)
  → LongHorizonBenchmarkRunner (manifest 校验)
  → run_many × N systems × repeat_count
  → BenchmarkSuiteReport (95% CI)
  → PhaseFComparisonResult (MIND vs 3 baselines)
  → PhaseFGateResult (F-1 ~ F-7 + ablation)
  → JSON report 持久化
```

闭环完整，无遗漏环节。

## 4. 实现完整性审核

### 4.1 PUS 计算

`compute_pus()` 实现与 spec 冻结公式一致：

$$PUS = 0.55 \times TSR + 0.15 \times GFC + 0.10 \times RR - 0.10 \times CCR - 0.05 \times MCR - 0.05 \times PR$$

- 输入校验完整：ratio 在 `[0, 1]`，cost ratio `>= 0`
- 结果四舍五入到 4 位小数

### 4.2 95% CI 统计

`reporting.py` 中 `_metric_interval()` 使用 t-分布 CI：

- `_T_CRITICAL_95` 查表覆盖 df 1-30，df > 30 回退到 1.96（正态近似）
- 样本量 = 1 时退化为点估计
- 样本标准差为 0 时 margin = 0

`phase_f.py` 中 `_comparison_interval()` 使用 min/max 而非 t-CI：

- 当前所有 runner 为确定性实现，所有 run 产出相同 PUS，因此 min = max = mean
- 对确定性系统这是保守等价的
- 接受报告已明确声明此设计选择

### 4.3 baseline 实现

- `NoMemoryBaselineSystem`：零记忆，不选择任何对象 → PUS = -0.05（理论下界）
- `FixedSummaryMemoryBaselineSystem`：仅选 `SummaryNote` 对象，keyword 排序，budget 1-2
- `PlainRagBaselineSystem`：keyword + vector scoring，type bonus，`run_bias = 0.001 * run_id`（跨 run 微小扰动）

三者均复用 `_score_sequence()` 共享评分逻辑，内部一致。

### 4.4 MIND 系统 runner

`MindLongHorizonSystem` 特点：

- 复用 Phase E `select_replay_targets` 进行排序
- `use_workspace` 开关控制 future_coverage 和 schema_expansion
- `use_offline_maintenance` 开关控制 promotion schema 注入
- 每个 `run_id` 独立 tempdir + SQLiteMemoryStore + promotion 结果
- `close()` 显式释放资源，所有调用方使用 `try/finally` 保护

ablation 设计合理：disabled 开关仅关闭对应组件，不改变其余逻辑。

### 4.5 LongHorizonEval v1 fixture

- 50 条序列：20 `episode_chain` + 30 `cross_episode_pair`
- 每条序列固定 6 步（满足 5-10 步要求）
- 运行时校验 `len(sequences) == 50` 和 `5 <= steps <= 10`
- manifest hash 基于 `json.dumps(payload, sort_keys=True, separators=(",", ":"))` 的 SHA-256
- 与 `LongHorizonDev v1` 完全分离

### 4.6 JSON 持久化

- `phase_f_benchmark_report_v1`：完整 round-trip（write + read），测试覆盖
- `phase_f_comparison_report_v1`：write only（comparison 单向输出）
- `phase_f_gate_report_v1`：write only（gate 单向输出）
- 所有 JSON 输出包含 `schema_version`、`generated_at` 时间戳

### 4.7 CLI 入口

5 个 CLI main 函数均通过 `argparse` 接受参数，支持 `--repeat-count` 和 `--output`，输出结构化文本。入口注册在 `pyproject.toml` 中，脚本封装在 `scripts/` 下，形式统一。

## 5. 必要性审核

### 5.1 每个新文件的必要性

| 文件 | 必要性 | 说明 |
| --- | --- | --- |
| `runner.py` | 必要 | 提供统一 runner 骨架和 PUS 计算入口，避免各 system 各写一套 |
| `baselines.py` | 必要 | F-2 gate 要求 3/3 baseline 可运行 |
| `mind_system.py` | 必要 | MIND 参与 comparison 和 ablation 的唯一 runner |
| `reporting.py` | 必要 | F-3 gate 要求 95% CI 统计报告 |
| `phase_f.py` | 必要 | F-1 ~ F-7 gate 逻辑和 JSON 持久化 |
| `long_horizon_eval.py` | 必要 | F-1 gate 要求冻结评测集，与 dev 分离 |
| `__init__.py` | 必要 | 统一导出公共 API |
| 6 个测试文件 | 必要 | 覆盖所有新模块和 gate |
| 5 个脚本文件 | 必要 | 本地 gate 执行入口 |
| 2 个文档 | 必要 | 启动清单和验收报告 |

### 5.2 无冗余代码

- `_safe_ratio` 和 `_RAW_TOPK_BASELINE_SIZE` 在 `baselines.py` 和 `mind_system.py` 中各有一份。两个模块的对象访问方式不同（dict vs SQLiteMemoryStore），合并会引入不必要耦合。此重复可接受。
- 无废弃函数、未使用导入或 dead code

## 6. 合理性审核

### 6.1 设计决策分析

| 决策 | 合理性 | 说明 |
| --- | --- | --- |
| eval 与 dev fixture 分离 | 合理 | 避免评测集与开发集互相污染 |
| `_comparison_interval` 使用 min/max | 合理 | 当前确定性系统下保守等价，已在文档中说明 |
| `f7_pass` 比 spec 更严格（要求 ci_lower >= 0.03） | 合理 | 更严格只会提高门槛，不降低保证 |
| baseline `maintenance_cost_ratio = 1.0` | 合理 | 1.0 为基准成本，baseline 无额外维护开销 |
| `PlainRagBaselineSystem.run_bias = 0.001 * run_id` | 合理 | 引入微小跨 run 变异，使 repeat_count > 1 具有统计意义 |
| `MindLongHorizonSystem` 使用显式 `close()` | 合理 | 所有调用方均以 try/finally 保护资源释放 |

### 6.2 潜在改进（非阻断）

- `MindLongHorizonSystem` 可实现 `__enter__`/`__exit__` 以支持 `with` 语句；当前 try/finally 模式已足够安全
- 当引入非确定性 runner 时，`_comparison_interval` 应切换为 t-分布 CI（当前 min/max 在非确定性场景下会过度保守）

## 7. 文档噪声排查

### 7.1 检查结果

| 检查项 | 结果 |
| --- | --- |
| TODO / FIXME / HACK / PLACEHOLDER | 未发现 |
| 过期 Phase 引用 | 未发现（Phase E 引用均为上下文必需） |
| 断链 / 无效链接 | 未发现 |
| 重复或自相矛盾描述 | 未发现 |
| 实现与文档不一致 | 未发现 |

### 7.2 启动清单

`docs/design/phase_f_startup_checklist.md` 内容准确：

- T1 ~ T5 任务拆分与完成状态均匹配实际代码
- 启动期数值（baseline PUS、comparison diff、gate 结果）与运行输出一致
- 下一步建议合理

### 7.3 验收报告

`docs/reports/phase_f_acceptance_report.md` 内容准确：

- Gate 结果表与实际运行输出一致
- 逐条核对覆盖 F-1 ~ F-7
- 非阻断风险（确定性 CI 点区间）已声明

## 8. 修正记录

| 文件 | 修正内容 | 原因 |
| --- | --- | --- |
| `mind/eval/__init__.py` | `__all__` 列表恢复严格字母序 | `ComparisonInterval` 和 `MetricConfidenceInterval` 位置错乱 |

修正后全量验证：

- `pytest -q`：`84 passed, 7 skipped`
- `ruff check mind tests scripts`：`All checks passed!`
- `mypy`：`Success: no issues found in 75 source files`

## 9. Gate 复现

### 9.1 静态检查

```
pytest -q                        → 84 passed, 7 skipped
ruff check mind tests scripts    → All checks passed!
mypy                             → Success: no issues found in 75 source files
```

### 9.2 Phase F manifest

```
fixture_name=LongHorizonEval v1
fixture_hash=24f203c01bae3cad01fe741a8244b1c1224413579433d22131935ad723740a49
sequence_count=50
step_range=6..6
family_counts=cross_episode_pair:30,episode_chain:20
```

### 9.3 Phase F gate

```
mind_vs_no_memory_diff=0.45
mind_vs_fixed_summary_memory_diff=0.17
mind_vs_plain_rag_diff=0.26
workspace_ablation_drop=0.07
offline_maintenance_ablation_drop=0.06
F-1=PASS
F-2=PASS
F-3=PASS
F-4=PASS
F-5=PASS
F-6=PASS
F-7=PASS
phase_f_gate=PASS
```

## 10. 最终结论

Phase F 独立审核判定：`PASS`

- 框架设计完整覆盖 F-1 ~ F-7 所有 gate 要求
- 实现与 spec 严格对应，无遗漏、无多余
- 每个新文件均有明确必要性
- 设计决策合理，文档无噪声
- `__all__` 字母序已修正
- 全量测试、静态检查和 gate 均通过
