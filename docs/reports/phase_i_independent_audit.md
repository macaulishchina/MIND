# Phase I 独立审计报告

审计日期：`2026-03-10`

审计对象版本：

- `git HEAD = 019fb20`
- 本报告对应对象为 `019fb20` 之后、尚未提交的本地工作树（包含 Phase I runtime access modes 全部改动）

## 1. 审计范围

本次审计覆盖 Phase I（Runtime Access Modes）的全部未提交改动，共涉及以下文件：

### 新增文件

| 文件 | 用途 |
| --- | --- |
| `mind/access/__init__.py` | Phase I access 模块公开 API |
| `mind/access/contracts.py` | 运行时 access mode 合约（请求 / 响应 / trace） |
| `mind/access/service.py` | 运行时 access 执行服务（fixed + auto） |
| `mind/access/benchmark.py` | AccessDepthBench v1 评测执行逻辑 |
| `mind/access/phase_i.py` | Phase I formal gate 评估 / 断言 / 报告 |
| `mind/fixtures/access_depth_bench.py` | AccessDepthBench v1 fixture 生成器 |
| `scripts/run_phase_i_gate.py` | Phase I gate CLI wrapper |
| `tests/test_access_contracts.py` | 合约正 / 反向测试 |
| `tests/test_access_service.py` | AccessService 固定档位 / auto 调度测试 |
| `tests/test_access_benchmark.py` | AccessDepthBench v1 全量基准测试 |
| `tests/test_phase_i_gate.py` | Phase I formal gate 端到端测试 |
| `docs/reports/phase_i_acceptance_report.md` | Phase I 验收报告 |
| `artifacts/phase_i/gate_report.json` | Phase I gate 持久化 JSON 工件 |

### 修改文件

| 文件 | 改动 |
| --- | --- |
| `mind/cli.py` | 新增 `phase_i_gate_main()` 函数与 `.access` 导入 |
| `pyproject.toml` | 新增 `mind-phase-i-gate` entry point |
| `docs/README.md` | 更新文档索引，增加 Phase I 验收报告与入口 |
| `artifacts/phase_h/gate_report.json` | 仅 `generated_at` 时间戳更新 |

## 2. 审计方法

1. 读取全部 diff，逐文件通读实现
2. 对照 `docs/foundation/phase_gates.md` 中 Phase I gate spec（`I-1 ~ I-8`）逐条验证阈值、验证方式与代码实现的一致性
3. 运行完整静态检查（`ruff check`、`mypy`）
4. 运行完整测试套件（`pytest -q`）
5. 运行前序 gate 回归（Phase C / H / G）
6. 运行 Phase I formal gate（`scripts/run_phase_i_gate.py`）
7. 编写 18 条补充测试，覆盖原有测试未涉及的 contract 反向验证、服务错误处理、auto 调度路径与 trace 完整性

## 3. 审计结论

Phase I 本次审计结论：**无阻断缺陷，PASS**

## 4. Gate Spec 对齐审查

| Gate | 规范阈值 | 代码实现阈值 | 一致性 |
| --- | --- | --- | --- |
| `I-1` | 5/5 mode 全部可调用；trace coverage = 100% | `len(set(callable_modes)) == 5 and trace_coverage_count == trace_total` | 完全一致 |
| `I-2` | `TimeBudgetHitRate >= 0.95`，`ConstraintSatisfaction >= 0.95` | `flash_time_budget_hit_rate >= 0.95 and flash_constraint_satisfaction >= 0.95` | 完全一致 |
| `I-3` | `AQS >= 0.75`，`MUS >= 0.65` | `recall_answer_quality_score >= 0.75 and recall_memory_use_score >= 0.65` | 完全一致 |
| `I-4` | `AnswerFaithfulness >= 0.95`，`GoldFactCoverage >= 0.90` | `reconstruct_answer_faithfulness >= 0.95 and reconstruct_gold_fact_coverage >= 0.90` | 完全一致 |
| `I-5` | `AnswerFaithfulness >= 0.97`，`GoldFactCoverage >= 0.92`，`ConstraintSatisfaction >= 0.98` | `reflective_answer_faithfulness >= 0.97 and reflective_gold_fact_coverage >= 0.92 and reflective_constraint_satisfaction >= 0.98` | 完全一致 |
| `I-6` | `auto` AQS 平均降幅 `<= 0.02`，`CostEfficiencyScore` 不低于 family-best | `auto_frontier_average_aqs_drop <= 0.02 and auto_frontier_cost_regression_count == 0` | 完全一致 |
| `I-7` | `upgrade / downgrade / jump` 各 > 0；震荡 `<= 5%`；无原因码 `= 0` | `upgrade_count > 0 and downgrade_count > 0 and jump_count > 0 and missing_reason_code_count == 0 and oscillation_rate <= 0.05` | 完全一致 |
| `I-8` | 显式固定档位被覆盖比例 `= 0` | `fixed_lock_override_count == 0` | 完全一致 |

## 5. 多维度审查结果

### 5.1 必要性

- Phase I 是阶段依赖链（H → I → J → K）中的必要环节
- 没有发现超出 Phase I 范围的改动（无 governance / persona / erase 越界）
- 没有新增独立于现有 primitives 的新"访问深度 primitive"，符合 spec 的 "明确不要求" 约束
- Phase I 引入 `mind/access/` 包结构合理，不侵入已有 `mind/kernel/`、`mind/primitives/` 或 `mind/governance/`

### 5.2 完整性

- 5 种 access mode（Flash / Recall / Reconstruct / Reflective / auto）全部实现
- 合约层（contracts.py）定义了完整的请求 / 响应 / trace event / trace / response 模型，带 Pydantic 校验器
- 服务层（service.py）实现了 fixed-mode 执行（`_run_locked`）和 auto 调度（`_run_auto`）
- 评测层（benchmark.py）实现了 AccessDepthBench v1 全量 benchmark，覆盖质量 / 性能 / 成本三维
- 门控层（phase_i.py）实现了 I-1 ~ I-8 formal gate 与 assert / report 输出
- Fixture 层（access_depth_bench.py）从 GoldenEpisodeSet 生成 60 个固定测试案例（20 × 3 家族）
- CLI（cli.py）和 pyproject.toml 配置齐全
- 验收报告和文档索引已更新

### 5.3 合理性

- **合约设计**：`AccessModel` 统一使用 `ConfigDict(extra="forbid", frozen=True)` 确保不可变和严格校验
- **Trace 强制约束**：trace 必须以 `select_mode` 开始、以 `mode_summary` 结束；fixed mode 不允许 auto 切换；auto 的 `resolved_mode` 不得为 AUTO；switch 事件必须附带 `reason_code`
- **Response 强制约束**：Flash 只能返回 `RAW_TOPK`；非 Flash 必须返回 WORKSPACE；Reflective 必须带 `verification_notes`；非 Reflective 禁止带 `verification_notes`
- **评分公式**：AQS = 0.45×TaskCompletion + 0.20×Constraint + 0.20×GoldFact + 0.15×Faithfulness；MUS = 0.40×Recall@20 + 0.30×SupportPrecision + 0.30×TraceSupport；OnlineCostRatio = 0.40×Context + 0.15×Generation + 0.20×Read + 0.25×Latency — 权重设计合理
- **`_ModePlan` 分级**：Flash(3/1/1) < Recall(8/4/4) < Reconstruct(12/6/6+expand) < Reflective(12/6/6+expand+verify) — 逐级递增，符合深度递进
- **Auto 调度**：基于 task_family 做初始选择，单次 switch 上限，避免震荡；不会在 fixed 锁定下覆盖用户选择

### 5.4 边界条件

- 空候选列表：`_execute_mode` 在候选为空时抛出 `AccessServiceError` ✓
- 无扩展 source_refs：带 `if expanded_object_ids:` 分支保护 ✓
- 除零保护：`_safe_ratio` 在 baseline = 0 时使用 1.0 ✓
- 空 gold_ids / actual_ids：`_coverage` 和 `_faithfulness` 在空输入时返回 0.0 ✓
- `_is_accessible`：检查 StoreError / concealed / invalid 状态 ✓

### 5.5 DRY / 代码质量

- 没有发现重复代码
- `_MODE_PLANS` 字典驱动模式差异，避免 if/else 堆叠
- 评测指标统一通过 `_aggregate_runs` 聚合，避免手工循环
- 前沿比较统一通过 `_build_frontier_comparisons` 构建
- `_merge_ids` 在 auto 路径合并候选集时去重

## 6. 发现的缺陷

**未发现功能性缺陷。**

## 7. 观察项（非阻断）

| 编号 | 描述 | 严重程度 |
| --- | --- | --- |
| OBS-1 | `phase_i.py` 中 auto 运行的 trace_coverage 直接加 `audited_run_count`，未逐条调用 `_trace_is_complete`。由于 Pydantic 校验器在 `AccessRunTrace` 构建时已强制 trace 结构完整，因此功能正确，但与 fixed_runs 的处理方式不一致 | LOW |
| OBS-2 | `_choose_auto_switch` 限制最多一次 switch。当前 benchmark 中 auto 以"初始选择 + 可选一次切换"足以通过 I-7，但后续 benchmark 分布变化可能需要支持多次切换 | LOW |
| OBS-3 | `_meets_family_floor` 对 `HIGH_CORRECTNESS` 没有显式检查 `task_family`，而是通过 mode-specific 条件过滤。逻辑正确，但可读性略低于前两个 family 的显式分支 | LOW |

## 8. 补充测试

本次审计新增 18 条补充测试：

### test_access_contracts.py (+12)

| 测试 | 覆盖点 |
| --- | --- |
| `test_response_rejects_flash_with_workspace_context` | Flash + WORKSPACE → 拒绝 |
| `test_response_rejects_non_flash_with_raw_topk_context` | 非 Flash + RAW_TOPK → 拒绝 |
| `test_response_rejects_reflective_without_verification_notes` | Reflective 无 notes → 拒绝 |
| `test_response_rejects_non_reflective_with_verification_notes` | 非 Reflective 有 notes → 拒绝 |
| `test_response_rejects_resolved_mode_auto` | resolved_mode = AUTO → 拒绝 |
| `test_response_rejects_workspace_without_selected_ids` | WORKSPACE 无 selected_ids → 拒绝 |
| `test_switch_event_rejects_same_from_and_target_mode` | from_mode == mode → 拒绝 |
| `test_non_initial_switch_requires_from_mode` | 非 INITIAL 无 from_mode → 拒绝 |
| `test_non_select_event_rejects_switch_metadata` | READ 事件附带 switch 元数据 → 拒绝 |
| `test_trace_rejects_missing_final_mode_summary` | trace 无 mode_summary 结尾 → 拒绝 |
| `test_trace_final_summary_must_match_resolved_mode` | 最终 mode_summary 与 resolved_mode 不一致 → 拒绝 |
| `test_access_depth_bench_v1_task_families_are_balanced` | 60 个 case，每 family 20 个，ID 唯一 |

### test_access_service.py (+6)

| 测试 | 覆盖点 |
| --- | --- |
| `test_service_rejects_invalid_request_dict` | 非法 mode 值 → AccessServiceError |
| `test_service_rejects_missing_task_id` | 缺少 task_id → AccessServiceError |
| `test_auto_balanced_stays_at_recall_without_switch` | balanced auto 无触发 → 保持 recall，单一 select_mode |
| `test_auto_high_correctness_starts_at_reconstruct` | HIGH_CORRECTNESS auto → 初始 reconstruct |
| `test_flash_trace_has_exactly_four_events` | Flash trace 结构 = select/retrieve/read/summary |
| `test_all_trace_events_carry_non_auto_mode` | 所有 5 种 mode 的 trace 事件均不使用 AUTO |

## 9. 验证结果

| 验证项 | 结果 |
| --- | --- |
| `.venv/bin/ruff check mind tests scripts` | `All checks passed!` |
| `.venv/bin/mypy` | `Success: no issues found in 109 source files` |
| `.venv/bin/pytest -q` | `192 passed, 11 skipped` |
| `python3 scripts/run_phase_c_gate.py` | `phase_c_gate=PASS` |
| `python3 scripts/run_phase_h_gate.py` | `phase_h_gate=PASS` |
| `python3 scripts/run_phase_g_gate.py` | `phase_g_gate=PASS` |
| `python3 scripts/run_phase_i_gate.py` | `phase_i_gate=PASS`（I-1 ~ I-8 全部 PASS） |

## 10. Phase J 就绪性评估

Phase I 成功建立了"可执行、可评测、可 trace 的运行时 access depth 层"。以下是进入 `Phase J / Unified CLI Experience` 的前提确认：

| 前提 | 状态 |
| --- | --- |
| 5 种 access mode 可独立调用 | ✓ |
| auto 调度具名 trace + 切换可解释 | ✓ |
| 固定档位不被 auto 覆盖 | ✓ |
| 质量 / 性能 / 成本三维 benchmark 已建立 | ✓ |
| 前序 gate（C / G / H）未回归 | ✓ |
| 无新增存储 schema（不需要新 migration） | ✓ |

Phase J 的核心任务：把现有 primitive、access、offline、governance、gate 和 report 收敛到统一的 `mind` CLI 入口，并冻结统一 help、profile/backend 切换、输出 contract 和 demo 路径。Phase I 提供的稳定 runtime access 底盘，是这个统一体验层成立的必要前提。

原先更重的治理执行工作已顺延到 `Phase N / Governance / Reshape`；Phase J 不再承担 mixed-source rewrite、`erase_scope` 或 artifact cleanup 的正式实现责任。

## 11. 最终结论

**Phase I 审计结论：PASS — 无缺陷，18 条补充测试已通过，可安全进入 `Phase J / Unified CLI Experience`。**
