# Phase G 启动清单

时点说明：这份文档记录的是 Phase F 验收通过后，Phase G 从启动到本地正式验收通过的收敛轨迹。当前正式通过口径见 [../reports/phase_g_acceptance_report.md](../reports/phase_g_acceptance_report.md) 和 [../reports/phase_g_independent_audit.md](../reports/phase_g_independent_audit.md)；这里保留任务拆分、推进顺序和启动期基线，供后续追溯。

## 目标

先把 Phase G 的优化对象和比较口径冻结，再逐步做预算对齐、优化策略和正式 gate：

1. 冻结 `fixed-rule` 策略基线，避免后续“优化对象”漂移
2. 建立预算与成本报表骨架，明确 token / storage / maintenance 的同预算约束
3. 落地 `optimized strategy v1`
4. 建立 `G-1 ~ G-5` comparison / family / pollution 评估器
5. 补齐 Phase G 验收报告与独立审计

## 任务拆分

1. `T1`：冻结 `fixed-rule` 策略基线与 Phase G 启动文档
2. `T2`：预算会计与 `cost report` 骨架
3. `T3`：`optimized strategy v1`
4. `T4`：`G-1 ~ G-5` eval / per-family / pollution audit
5. `T5`：Phase G gate、验收报告和独立审计

## 当前进度

- `T1` 已完成
- `T2` 已完成
- `T3` 已完成
- `T4` 已完成
- `T5` 已完成（本地 gate / 验收 / 独立审计）

## 本次已完成

- 新增 `mind/eval/strategy.py`
  - 冻结 `FixedRuleMindStrategy`
  - 抽出 `StrategyStepDecision` 和 `MindStrategy` 接口
  - 把 step-level 选择语义从 `MindLongHorizonSystem` 中独立出来
- `MindLongHorizonSystem` 现在接受显式 strategy 注入
  - 默认仍然使用 `fixed_rule_v1`
  - 当前 Phase F 的行为与通过口径保持不变
- 新增 `tests/test_eval_strategy.py`
  - 验证固定规则策略的默认决策
  - 验证显式注入 `FixedRuleMindStrategy` 时与默认系统等价
- 新增 `mind/eval/costing.py`
  - 冻结 `phase_g_cost_report_v1`
  - 建立 `CostBudgetProfile`、`PhaseGCostReport` 和 fixed-rule budget baseline
- `MindLongHorizonSystem` 现在暴露 `cost_snapshot(run_id)`
  - 显式记录每个 run 的 `base_object_count / generated_schema_count / storage_cost_ratio`
- 新增 `mind-phase-g-cost-report` / `scripts/run_phase_g_cost_report.py`
  - 输出 fixed-rule 策略的 token / storage / maintenance / total cost report
- 新增 `tests/test_eval_costing.py`
  - 验证 Phase G cost report round-trip
  - 验证 fixed-rule budget profile 被正确冻结

当前 fixed-rule budget baseline：

- `token_cost_ratio=0.10`
- `storage_cost_ratio=1.20`
- `maintenance_cost_ratio=1.10`
- `total_cost_ratio=2.40`
- `total_budget_bias=0.00`

- 新增 `OptimizedMindStrategy`（`optimized_v1`）
  - 保持总 handle budget 不变
  - 把最后一步的一个 handle 重分配给更高价值、可直接补全的双对象 step
  - 对当前 step 的 direct needed objects 施加轻量 bonus，减少固定规则在 tie 情况下的低效选择
- 新增 `mind-phase-g-strategy-dev` / `scripts/run_phase_g_strategy_dev.py`
  - 输出 fixed-rule 与 `optimized_v1` 的单次 dev 对比
- `tests/test_eval_strategy.py` 已补充：
  - budget schedule 验证
  - `optimized_v1` 在不改变 `context_cost_ratio / storage_cost_ratio / maintenance_cost_ratio` 的前提下，单次 run `PUS` 高于 fixed-rule

当前 `optimized_v1` dev 对比结果：

- `fixed_rule_pus=0.40`
- `optimized_v1_pus=0.48`
- `pus_delta=0.08`
- `fixed_rule_context_cost_ratio=0.10`
- `optimized_v1_context_cost_ratio=0.10`
- `fixed_rule_storage_cost_ratio=1.20`
- `optimized_v1_storage_cost_ratio=1.20`

当前本地 gate 结果：

- `pus_improvement=0.08`
- `cross_episode_pair_pus_delta=0.08`
- `episode_chain_pus_delta=0.08`
- `token_budget_bias=0.00`
- `storage_budget_bias=0.00`
- `maintenance_budget_bias=0.00`
- `total_budget_bias=0.00`
- `pollution_rate_delta=0.00`
- `G-1 ~ G-5` 全部通过
- 当前正式通过口径见 [../reports/phase_g_acceptance_report.md](../reports/phase_g_acceptance_report.md) 和 [../reports/phase_g_independent_audit.md](../reports/phase_g_independent_audit.md)

## 当前边界

- 启动期曾缺少 Phase G comparison / gate
- 当前这些边界都已关闭；正式通过口径以 [../reports/phase_g_acceptance_report.md](../reports/phase_g_acceptance_report.md) 为准

## 下一步

1. 若需要更强外部背书，可在更大任务分布或非确定性评测设置下继续复核
2. 后续工作应转向更真实任务分布、非确定性评测和服务化演进，而不是继续停留在 Phase G 启动清单
