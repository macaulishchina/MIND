# Phase F 启动清单

时点说明：这份文档记录的是 Phase E 验收通过后，Phase F 从启动到本地正式验收通过的收敛轨迹。当前正式通过口径见 [../reports/phase_f_acceptance_report.md](../reports/phase_f_acceptance_report.md)；这里保留任务拆分、推进顺序和启动期基线，供后续追溯。

## 目标

先把 Phase F 的评测基础设施做扎实：

1. 冻结 `LongHorizonEval v1`
2. 冻结 eval manifest，确保所有 run 绑定同一 hash
3. 建立可复用 benchmark runner，而不是让 MIND 和 baseline 各写一套临时脚本
4. 再逐步补齐 3 个 baseline、统计报告、对比实验和 ablation

## 任务拆分

1. `T1`：`LongHorizonEval v1 + eval manifest + benchmark runner skeleton`
2. `T2`：`no-memory / plain RAG / fixed summary memory` 三个 baseline runner
3. `T3`：多次独立运行、结果落盘、`95% CI` 统计报告
4. `T4`：`F-4 ~ F-6` benchmark comparison
5. `T5`：`workspace / offline maintenance` ablation、Phase F 验收和独立审计

## 当前进度

- `T1` 已完成
- `T2` 已完成
- `T3` 已完成
- `T4` 已完成
- `T5` 已完成（本地 gate / 验收）
- `Phase F` 第三方独立审计已完成，见 [../reports/phase_f_independent_audit.md](../reports/phase_f_independent_audit.md)

## 本次已完成

- 新增 `mind/fixtures/long_horizon_eval.py`
  - 冻结 `LongHorizonEval v1 = 50` 条序列
  - family 分布固定为 `episode_chain=20`、`cross_episode_pair=30`
  - 每条序列固定 `6` 步，满足 `5~10` 步要求
  - 当前 manifest hash：`24f203c01bae3cad01fe741a8244b1c1224413579433d22131935ad723740a49`
- 新增 `mind/eval/runner.py`
  - 冻结 `PUS` 计算入口
  - 新增 `LongHorizonBenchmarkRunner`、`LongHorizonScoreCard`
  - 为后续 MIND 和 3 个 baseline 提供统一 runner 骨架
- 新增 `mind-phase-f-manifest` / `scripts/run_phase_f_manifest.py`
  - 输出 `LongHorizonEval v1` 的固定 manifest 和 hash
- 新增 `mind/eval/baselines.py`
  - 落地 `no-memory / fixed summary memory / plain RAG` 三个 baseline runner
  - 三者共享同一份 `LongHorizonEval v1` 和同一套 sequence-level `PUS` 评分逻辑
- 新增 `mind-phase-f-baselines` / `scripts/run_phase_f_baselines.py`
  - 输出三个 baseline 的单次运行指标
- 新增 `mind/eval/reporting.py`
  - 冻结 benchmark JSON schema：`phase_f_benchmark_report_v1`
  - 支持 raw runs、metric summary、`95% CI` 和 JSON round-trip
- 新增 `mind-phase-f-report` / `scripts/run_phase_f_report.py`
  - 支持 `>= 3` 次重复运行
  - 默认持久化 Phase F baseline CI 报告
- 新增 `mind/eval/mind_system.py`
  - 落地 MIND 在 `LongHorizonEval v1` 上的当前系统 runner
  - 复用 workspace-style handle 选择和 offline promotion
- 新增 `mind-phase-f-comparison` / `scripts/run_phase_f_comparison.py`
  - 输出 `F-4 ~ F-6` 对比结果并持久化 comparison report
- 新增 `mind-phase-f-gate` / `scripts/run_phase_f_gate.py`
  - 统一执行 `F-1 ~ F-7` 本地 gate
  - 把 `workspace / offline maintenance` ablation 纳入同一 report

当前本地 baseline 单次结果：

- `no_memory_pus=-0.05`
- `fixed_summary_memory_pus=0.23`
- `plain_rag_pus=0.14`
- 当前这组冻结样例上，`fixed summary memory` 高于当前实现的 `plain RAG`
- 这不构成 Phase F 阻断；Phase F gate 只要求 baseline 可运行、可比较，不预设 baseline 之间的固定性能顺序

## 启动期边界（已收敛）

- 启动期曾缺少 `Phase F gate` 和 `F-7` ablation
- 当前这些边界都已关闭；正式通过口径以 [../reports/phase_f_acceptance_report.md](../reports/phase_f_acceptance_report.md) 为准

当前本地 CI report 基线：

- `repeat_count=3`
- `phase_f_benchmark_report_v1` 已可持久化
- 当前 3 个 baseline 均为确定性实现，因此 `95% CI` 收敛为点区间；这不阻断 T3，但后续正式 comparison 仍需保持 `>= 3` 次独立运行记录

当前本地 comparison 结果：

- `mind_pus_mean=0.40`
- `mind_vs_no_memory_diff=0.45`
- `mind_vs_fixed_summary_memory_diff=0.17`
- `mind_vs_plain_rag_diff=0.26`
- 当前 `F-2 ~ F-6` 均已通过

当前本地 gate 结果：

- `workspace_ablation_drop=0.07`
- `offline_maintenance_ablation_drop=0.06`
- `F-1 ~ F-7` 全部通过
- 当前正式通过口径见 [../reports/phase_f_acceptance_report.md](../reports/phase_f_acceptance_report.md)

## 下一步

1. 若需要外部背书，发起第三方独立审计
2. 进入 Phase G，开始“优化策略相对固定规则策略”的同预算收益验证
