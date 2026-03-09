# Phase E 启动清单

时点说明：这份文档记录的是 Phase D 验收通过后，Phase E 从启动到收敛的轨迹。当前正式通过口径见 [../reports/phase_e_acceptance_report.md](../reports/phase_e_acceptance_report.md)；这里保留的是启动期与中间收敛记录。

## 目标

先把 Phase E 的硬前置做扎实：

1. 有可验证的离线 job contract
2. 有可运行的 worker 批处理入口
3. 有最小 promotion policy，而不是把“promotion”继续停留在文档口头
4. 有 PostgreSQL jobs table 和 claim / complete / fail 生命周期
5. 有 `LongHorizonDev v1` 和 `ReplayLift` baseline

## 已完成

- `mind/offline/jobs.py`
  - 冻结 `OfflineJobKind`、`OfflineJobStatus`
  - 冻结 `reflect_episode / promote_schema` 两类 job payload
  - 定义 `OfflineJobStore` 协议和 `new_offline_job(...)` 构造器
- `mind/offline/service.py`
  - 新增 `OfflineMaintenanceService`
  - `reflect_episode` 走现有 `PrimitiveService.reflect`
  - `promote_schema` 走现有 `PrimitiveService.reorganize_simple`
- `mind/offline/promotion.py`
  - 新增 `assess_schema_promotion(...)`
  - 当前 v0 准入标准：至少两个对象、跨 episode 支持、无 success/failure 冲突
- `mind/offline/worker.py`
  - 新增单进程 `OfflineWorker.run_once(...)`
  - 支持 job kind 过滤、成功/失败结构化落账
- PostgreSQL
  - 新增 `offline_jobs` 表
  - claim 路径采用 `FOR UPDATE SKIP LOCKED + pg_try_advisory_xact_lock(...)`
  - Alembic 已增加 `20260309_0004_offline_jobs.py`
- CLI
  - 新增 `mind-offline-worker-once`
  - 对应脚本入口：`scripts/run_offline_worker_once.py`
- Long-horizon baseline
  - 新增 `mind/fixtures/long_horizon_dev.py`
  - 新增 `mind/offline/replay.py` 和 `mind/offline/phase_e.py`
  - 新增 `mind-phase-e-startup` / `scripts/run_phase_e_startup.py`

## 已验证

- `tests/test_offline_policy.py`
  - promotion 接受 cross-episode support
  - promotion 拒绝 conflicting reflections
- `tests/test_offline_worker.py`
  - worker 能跑通 `reflect_episode + promote_schema`
  - worker 能正确标记失败 job
- `tests/test_postgres_regression.py`
  - 已覆盖 `offline_jobs` enqueue / claim / complete / fail 生命周期
- `tests/test_phase_e_startup.py`
  - 已冻结 `LongHorizonDev v1 = 30` 条序列，每条 `5` 步
  - `ReplayLift`、`SchemaValidationPrecision`、`PromotionPrecision@10` baseline 已可跑并通过本地门槛
- `tests/test_phase_e_gate.py`
  - 已覆盖 `E-1 ~ E-5` 的 formal gate
  - `PUS / PollutionRate` 的 offline A/B dev eval 已进入 gate

当前本地 startup baseline：

- `long_horizon_sequences=30`
- `step_range=5..5`
- `promotion_sequences=10`
- `top_decile_reuse_rate=0.40`
- `random_decile_reuse_rate=0.19`
- `replay_lift=2.07`
- `audited_schema_count=10`
- `schema_validation_precision=1.00`
- `promotion_precision_at_10=1.00`

当前本地 formal gate：

- `source_trace_coverage=1.00`
- `replay_lift=2.07`
- `schema_validation_precision=1.00`
- `promotion_precision_at_10=1.00`
- `no_maintenance_pus=0.38`
- `maintenance_pus=0.52`
- `pus_improvement=0.14`
- `pollution_rate_delta=0.00`
- `phase_e_gate=PASS`

## 非阻断后续项

- 这份文档不再代表当前正式 gate 口径；当前通过口径以 [../reports/phase_e_acceptance_report.md](../reports/phase_e_acceptance_report.md) 为准
- 当前仍可继续补强：
  - 第三方独立审计
  - 在可用 DSN 环境里的 Phase E PostgreSQL 实测回归结果
  - 更大规模的 `LongHorizonEval v1`

## 下一步

1. 发起第三方独立审计
2. 在具备 DSN 的环境里执行 `mind-postgres-regression` 的 Phase E 路径
3. 进入 Phase F：`LongHorizonEval v1` 与 benchmark comparison
