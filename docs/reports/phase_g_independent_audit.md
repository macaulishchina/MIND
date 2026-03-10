# 阶段 G 独立审计报告

**审计日期:** `2026-03-10`  
**审计范围:** 所有本地未提交修改，覆盖策略优化层（Strategy Pattern）、成本核算框架（Cost Budget）、Phase G Gate 评估逻辑、CLI 入口、辅助脚本、文档  
**基准版本:** Phase G 全功能变更集  
**前置依赖:** Phase F gate PASS（本次审计中由 Phase G 间接回归验证）

---

## 1. 审计方法论

| 步骤 | 内容 |
|------|------|
| ① 收集差异 | `get_changed_files` 获取完整 diff；约 20 个新增/修改文件 |
| ② 逐文件通读 | 全部新增文件 + 所有修改行完整阅读（~2000 行新增代码） |
| ③ 规范对照 | 对照 `phase_gates.md` G-1 ~ G-5，逐条验证 |
| ④ 工具链检测 | `ruff check` / `mypy` / `pytest` |
| ⑤ Gate 脚本运行 | `python scripts/run_phase_g_gate.py --repeat-count 3` |
| ⑥ 多维度深度审计 | 必要性、完整性、合理性、DRY、防御性编码、边界条件 |
| ⑦ 缺陷修复 | 修复 DEF-1（CI 辅助函数重复）、DEF-2（比较区间重复） |
| ⑧ 补充测试 | 新增 32 条边界/深度测试覆盖审计发现的薄弱点 |
| ⑨ 全量回归验证 | 修复后重新运行 ruff + mypy + pytest + Phase G gate |

---

## 2. 基线检测结果（修复前）

```
$ ruff check mind tests scripts
All checks passed!

$ mypy
Success: no issues found in 84 source files

$ pytest tests/ -q
91 passed, 7 skipped in 44.36s
# 7 skipped: Postgres 回归测试（需 MIND_POSTGRES_DSN 环境变量）

$ python scripts/run_phase_g_gate.py --repeat-count 3
G-1=PASS  G-2=PASS  G-3=PASS  G-4=PASS  G-5=PASS
phase_g_gate=PASS
pus_improvement=0.08
```

---

## 3. Gate 逐条验证

### G-1：同预算下策略收益 — PUS ≥ +0.05

| 比较对 | PUS delta | 判定 |
|--------|-----------|------|
| cross_episode_pair | +0.08 | PASS |
| episode_chain | +0.08 | PASS |

`OptimizedMindStrategy` vs `FixedRuleMindStrategy` 在 `LongHorizonEval v1` 上实测 PUS 提升 +0.08，超越阈值 +0.05。

**判定: G-1 PASS**

### G-2：预算偏差 ≤ 5%

| 指标 | 偏差 | 阈值 | 判定 |
|------|------|------|------|
| token_budget_bias | 0.00 | ≤ 5% | PASS |
| storage_budget_bias | 0.00 | ≤ 5% | PASS |
| maintenance_budget_bias | 0.00 | ≤ 5% | PASS |
| total_budget_bias | 0.00 | ≤ 5% | PASS |

优化策略在完全不增加成本的前提下获得 PUS 提升——预算偏差为零，表明 `optimized_budget_schedule` 是纯重分配而非额外消耗。

**判定: G-2 PASS**

### G-3：泛化覆盖 — 改进覆盖 ≥ 2 个任务家族

- 改进出现在 2 个任务家族（cross_episode_pair, episode_chain）
- 满足 `>= 2` 阈值

**判定: G-3 PASS**

### G-4：污染控制 — PollutionRate 增幅 ≤ 0.02

- pollution_rate_delta = 0.00
- 远低于 0.02 阈值

**判定: G-4 PASS**

### G-5：统计稳定性 — ≥ 3 次独立运行，CI 下界 > 0

- repeat_count = 3
- PUS improvement 95% CI lower bound = 0.08（确定性系统，方差为零）
- CI lower > 0

**判定: G-5 PASS**

---

## 4. 变更清单

### 4.1 Phase G 实现新增文件

| 文件 | 行数 | 说明 |
|------|------|------|
| `mind/eval/strategy.py` | 288 | 策略抽象层：`MindStrategy` 接口、`FixedRuleMindStrategy`（冻结 Phase F 基线）、`OptimizedMindStrategy`（预算重分配 + 直接需求奖励） |
| `mind/eval/costing.py` | 391 | 成本核算：`CostBudgetProfile`、`PhaseGCostReport`、`evaluate_fixed_rule_cost_report`、JSON round-trip |
| `mind/eval/phase_g.py` | 330 | Gate 评估逻辑：`PhaseGGateResult`（g1~g5 计算属性）、`evaluate_phase_g_gate`、`assert_phase_g_gate` |
| `scripts/run_phase_g_cost_report.py` | ~30 | CLI wrapper：成本报告 |
| `scripts/run_phase_g_strategy_dev.py` | ~30 | CLI wrapper：策略开发 |
| `scripts/run_phase_g_gate.py` | ~30 | CLI wrapper：gate 验证 |
| `tests/test_eval_strategy.py` | ~80 | 策略测试：4 条 |
| `tests/test_eval_costing.py` | ~50 | 成本报告测试：2 条 |
| `tests/test_phase_g_gate.py` | ~30 | Gate 集成测试：1 条 |
| `docs/design/phase_g_startup_checklist.md` | — | 启动检查清单 |
| `docs/reports/phase_g_acceptance_report.md` | — | 自验收报告 |

### 4.2 Phase G 修改文件

| 文件 | 修改内容 |
|------|----------|
| `mind/eval/mind_system.py` | 注入 `strategy: MindStrategy`；新增 `MindRunCostSnapshot`；`cost_snapshot()` 方法；步骤选择从内联逻辑委托到 `strategy.select_step_handles()` |
| `mind/eval/__init__.py` | 导出 Phase G 公共 API（~15 个符号） |
| `mind/cli.py` | 新增 `phase_g_cost_report_main`、`phase_g_strategy_dev_main`、`phase_g_gate_main` |
| `pyproject.toml` | 新增 3 个 script 入口 |
| `README.md`、`docs/README.md`、`docs/foundation/implementation_stack.md` | 状态文档更新 |

### 4.3 审计修复新增/修改文件

| 文件 | 行数 | 说明 |
|------|------|------|
| `mind/eval/_ci.py` | 100 | **新增** — 抽取共享 CI 辅助：`MetricConfidenceInterval`、`T_CRITICAL_95`、`t_critical()`、`metric_interval()` |
| `mind/eval/reporting.py` | — | **修改** — 从 `_ci` 导入，删除重复定义 |
| `mind/eval/costing.py` | — | **修改** — 从 `_ci` 导入，删除重复定义 |
| `mind/eval/phase_f.py` | — | **修改** — `_comparison_interval` → `comparison_interval`（公开化），保留私有别名 |
| `mind/eval/phase_g.py` | — | **修改** — 从 `phase_f` 导入共享 `comparison_interval`，删除重复定义 |
| `tests/test_phase_g_deep_audit.py` | 376 | **新增** — 32 条深度补充测试 |

---

## 5. 多维度审计

### 5.1 必要性

| 组件 | 必要性评估 |
|------|-----------|
| `MindStrategy` 接口 | **必要** — 将步骤选择策略从 `MindLongHorizonSystem` 中解耦，使基线 vs 优化策略可插拔、可独立测试 |
| `OptimizedMindStrategy` | **必要** — G-1 要求优化策略 PUS 提升 ≥ +0.05，必须有至少一个非平凡优化实现 |
| `FixedRuleMindStrategy` | **必要** — 冻结 Phase F 行为作为精确基线，保证 A/B 比较的公平性 |
| `CostBudgetProfile` | **必要** — G-2 要求预算偏差计算，需先固定固定规则下的成本基线 |
| `PhaseGCostReport` | **必要** — G-2 预算偏差和 G-4 污染控制需结构化成本报告 |
| `PhaseGGateResult` | **必要** — 编码 G-1~G-5 判定逻辑，实现自动化 gate 验证 |

### 5.2 完整性

| 检查项 | 结果 |
|--------|------|
| G-1~G-5 所有子门都有对应代码路径 | ✅ |
| 策略接口 `select_step_handles()` 在 `MindLongHorizonSystem` 中被正确调用 | ✅ |
| 成本快照 `cost_snapshot()` 在报告中被引用 | ✅ |
| CLI 入口可运行、script wrapper 与 pyproject.toml 对齐 | ✅ |
| JSON 序列化/反序列化往返测试 | ✅ |
| Phase F 行为后向兼容（默认系统 = 显式 FixedRule） | ✅（test_eval_strategy 验证） |
| Phase G gate 自我退化保护 | ✅（`assert_phase_g_gate` 在失败时抛异常） |

### 5.3 合理性

| 维度 | 评估 |
|------|------|
| 优化机制 | `optimized_budget_schedule`（最后一步 → 首个多对象步骤的预算重分配）+ `needed_object_bonus`（0.03 递减奖励）——简洁有效，不引入任何外部依赖或训练循环 |
| 策略 ID 版本化 | `strategy_id="fixed_rule_v1"` / `"optimized_v1"` — 可追溯 |
| Gate 计算属性 | `g1_pass` ~ `g5_pass` 为 `@property`，避免状态不一致 |
| CI 计算 | 使用 t 分布查表（df 1~30），df>30 回退到正态 z=1.96 — 合理且保守 |
| 错误处理 | `_relative_bias` 对 target≤0 抛 `ValueError`；`assert_phase_g_gate` 失败抛 `AssertionError` — 防御充分 |

---

## 6. 缺陷清单

### DEF-1（低风险 — 已修复）：CI 辅助函数代码重复

**位置:** `mind/eval/costing.py` vs `mind/eval/reporting.py`

**问题:** `_T_CRITICAL_95` 查找表（30 条）、`_metric_interval()` 函数、`_t_critical()` 函数在两个模块中完全相同复制。维护风险——未来修改需同步两处。

**修复:** 创建 `mind/eval/_ci.py` 作为规范定义，两个模块均从 `_ci` 导入。通过别名 `_metric_interval = metric_interval` 保持内部调用者兼容。

**验证:** ruff clean, mypy clean, 全量测试通过。

### DEF-2（低风险 — 已修复）：比较区间函数代码重复

**位置:** `mind/eval/phase_g.py` vs `mind/eval/phase_f.py`

**问题:** `_comparison_interval()` 和 `_comparison_interval_to_dict()` 在两个模块中完全相同复制。

**修复:** 将 `phase_f.py` 中的版本提升为公开函数 `comparison_interval()` / `comparison_interval_to_dict()`，`phase_g.py` 从 `phase_f` 导入共享版本。保留私有别名确保后向兼容。

**验证:** ruff clean, mypy clean, 全量测试通过。

---

## 7. 观察项（非阻塞）

| 编号 | 描述 | 风险 | 建议 |
|------|------|------|------|
| OBS-1 | `comparison_interval` 使用 range（min/max）而非 t-CI — 同 Phase F 行为一致 | 低 | 当前确定性系统下 min=max=mean，差异为 0。若未来引入非确定性因素需升级为真 t-CI |
| OBS-2 | `optimized_budget_schedule` 中 `target_index != donor_index` 守卫条件始终为 True（因 `first_completable_multi_object_step` 排除最后一步） | 极低 | 保留为防御性编码，无需修改 |
| OBS-3 | `phase_g_cost_report_main` 固定打印 "PASS" — 它是报告工具而非 gate 入口 | 低 | 后续可改为根据预算偏差判定，或在输出中区分"报告已生成"和"PASS/FAIL" |
| OBS-4 | `MindStrategy` 基类未使用 `abc.ABC` + `@abstractmethod` | 低 | 未来可加强类型约束，但当前仅两个子类，风险可控 |

---

## 8. 补充测试

本次审计新增 **32 条**深度边界测试（`tests/test_phase_g_deep_audit.py`，376 行），覆盖：

| 测试类 | 测试数 | 覆盖点 |
|--------|--------|--------|
| `TestMetricInterval` | 4 | 单值塌缩、相同值零宽度、离散值非零 CI、空序列异常 |
| `TestTCritical` | 4 | 已知 df=2、df=0 返回 0、df 负数返回 0、df>30 回退正态 |
| `TestComparisonInterval` | 2 | 相同值塌缩、长度不匹配异常 |
| `TestOptimizedBudgetSchedule` | 3 | 空序列返回空、单步无重分配、总预算守恒 |
| `TestFirstCompletableMultiObjectStep` | 1 | 无多对象步骤返回 None |
| `TestNeededObjectBonus` | 3 | 默认最多 3 个奖励、空 ID 返回空、零奖励返回空 |
| `TestRelativeBias` | 4 | 相同值零偏差、双倍值 100% 偏差、target=0 异常、target 负数异常 |
| `TestEvaluateFixedRuleCostReport` | 1 | repeat_count=0 抛异常 |
| `TestMindLongHorizonSystemCostSnapshot` | 3 | 未运行时异常、策略 ID 匹配、正整数计数 |
| `TestBudgetBiasWithinLimit` | 2 | 5% 以内 PASS、超过 5% FAIL |
| `TestAssertPhaseGGateFailures` | 1 | G-5 最低运行次数约束 |
| `TestPhaseGGateReportJson` | 1 | JSON 持久化往返 |
| `TestPhaseFBackwardCompatibility` | 1 | 默认系统与显式 FixedRule 全序列一致 |
| `TestHandleCoverage` | 2 | 非 schema 对象仅覆盖自身、schema 扩展禁用时仅覆盖自身 |

---

## 9. 最终验证结果（修复后）

```
$ ruff check mind tests scripts
All checks passed!

$ mypy
Success: no issues found in 86 source files

$ pytest tests/ -q
123 passed, 7 skipped in 61.59s

$ python scripts/run_phase_g_gate.py --repeat-count 3
G-1=PASS  (pus_improvement=0.08)
G-2=PASS  (token=0.00, storage=0.00, maintenance=0.00, total=0.00)
G-3=PASS  (2 families improved)
G-4=PASS  (pollution_rate_delta=0.00)
G-5=PASS  (3 runs, CI lower=0.08)
phase_g_gate=PASS
```

| 指标 | 修复前 | 修复后 | 变化 |
|------|--------|--------|------|
| ruff | clean | clean | — |
| mypy source files | 84 | 86 | +2（`_ci.py`、`test_phase_g_deep_audit.py`） |
| pytest passed | 91 | 123 | +32 |
| pytest skipped | 7 | 7 | — |
| Phase G gate | PASS | PASS | 无退化 |

---

## 10. 下一阶段就绪性评估

### 阶段 G 产物完备性

| 检查项 | 状态 |
|--------|------|
| G-1~G-5 全部 PASS | ✅ |
| 策略接口可扩展（支持未来策略迭代） | ✅ |
| 成本核算框架可量化、可序列化 | ✅ |
| 代码无重复（DEF-1、DEF-2 已修复） | ✅ |
| 测试覆盖充分（7 个原始 + 32 个补充 = 39 条 Phase G 测试） | ✅ |
| ruff / mypy / pytest 全部 clean | ✅ |

### Phase H 前置条件

`phase_gates.md` 中 **未定义 Phase H gate**。Phase G 是当前规范中最后一个正式阶段。后续如扩展新阶段，建议先在 `phase_gates.md` 中补充 gate 规范，再开始实现。

---

## 11. 结论

**Phase G gate: PASS**

Phase G 实现结构清晰、Gate 全项通过、代码质量良好。本次审计发现 2 个低风险代码重复问题（DEF-1、DEF-2），均已修复并验证。4 个非阻塞观察项记录在案。补充 32 条深度边界测试，测试总数从 91 提升至 123。

Phase G 已达到可提交状态。
