# Phase E 独立审计报告

审计日期：`2026-03-09`

审计对象版本：

- `git HEAD = 8203ef4` + 未提交的 Phase E 本地工作树

审计范围：

- 框架设计完整性
- 实现完整性
- 必要性
- 合理性
- 文档噪声排查

审计方法：

- 逐文件审阅 Phase E 新增 / 修改的全部代码与文档
- 逐条核对 [phase_gates.md](../foundation/phase_gates.md) 中 `E-1 ~ E-5` 指标与实现的对齐关系
- 在本地运行 `pytest -q`、`ruff check`、`mypy`、`run_phase_e_startup.py`、`run_phase_e_gate.py`
- 审阅 `docs/` 全量文档，排查与 Phase E 相关的噪声和过时引用

---

## 1. 审计结论

**Phase E 独立审计结论：PASS（附 2 项低风险观察）**

当前 Phase E 实现在框架设计完整性、实现完整性、必要性和合理性四个维度上均通过审查。代码质量好，测试覆盖到位，文档噪声已清理。可安全进入 Phase F。

---

## 2. 补充验证（本轮审计期间实际执行）

| 验证项 | 结果 |
| --- | --- |
| `python3 -m pytest -q` | `75 passed, 7 skipped` |
| `python3 -m ruff check mind tests scripts` | `All checks passed!` |
| `python3 -m mypy` | `Success: no issues found in 57 source files` |
| `python3 scripts/run_phase_e_startup.py` | `phase_e_startup=PASS` |
| `python3 scripts/run_phase_e_gate.py` | `phase_e_gate=PASS` |

---

## 3. 框架设计完整性审查

### 3.1 Phase E Gate 指标与实现对齐

| Gate ID | phase_gates.md 定义 | 代码实现 | 结论 |
| --- | --- | --- | --- |
| `E-1` | 新派生对象 `SourceTraceCoverage = 100%` | `phase_e.py` → `build_integrity_report(store.iter_objects())` 检查全量 store 的 trace 覆盖 | 对齐 |
| `E-2` | `SchemaValidationPrecision >= 0.85` | `audit.py` → `audit_schema_evidence(...)` 对每个 promotion schema 做 evidence ref token overlap 检查 | 对齐 |
| `E-3` | `ReplayLift >= 1.5` on `LongHorizonDev v1` | `replay.py` → `select_replay_targets(...)` + `future_reuse_rate(...)` + deterministic random baseline | 对齐 |
| `E-4` | `PromotionPrecision@10 >= 0.80` | `audit.py` → `audit_promotion_within_window(...)` 检查 promotion schema 在后续窗口内的复用和 active 状态 | 对齐 |
| `E-5` | 离线维护后 `PUS >= 0.05` 且 `PollutionRate delta <= 0.02` | `phase_e.py` → `_evaluate_offline_dev_eval(...)` 构建 no-maintenance / maintenance 两条路径的 A/B 比较 | 对齐 |

### 3.2 阶段依赖链

Phase E 依赖 Phase D 的稳定 workspace 和检索。审查发现：

- Phase E 通过 `build_phase_d_seed_objects()` 获取已验证的种子对象
- `OfflineMaintenanceService` 通过 `PrimitiveService` 复用 Phase C 的 primitive API
- `LongHorizonDev v1` 的 candidate_ids 来自 `GoldenEpisodeSet v1`
- 无跨阶段违规依赖

### 3.3 共享指标使用

- `SourceTraceCoverage`：复用 `integrity.py` 的 `build_integrity_report()`
- `ReplayLift`：自有实现，定义与 phase_gates.md 一致（top-decile vs random-decile 复用率之比）
- `PromotionPrecision@10`：自有实现，语义正确（promoted 对象在后续 10 步内未回滚且被复用）
- `PUS`：按 phase_gates.md 的公式 `0.55 * TaskSuccessRate + 0.15 * GoldFactCoverage + 0.10 * ReuseRate - 0.10 * ContextCostRatio - 0.05 * MaintenanceCostRatio - 0.05 * PollutionRate` 实现，系数完全匹配
- `PollutionRate`：定义为 `(不合格生成对象数 / 全部生成对象数)`，与 phase_gates.md 一致

---

## 4. 实现完整性审查

### 4.1 文件清单与职责

| 文件 | 职责 | 完整性 |
| --- | --- | --- |
| `mind/offline/__init__.py` | 公开 API 汇总 | 完整，`__all__` 覆盖所有公共符号 |
| `mind/offline/jobs.py` | Job contract / 数据模型 / 协议 | 完整，`OfflineJobKind`、`OfflineJobStatus`、payload models、`OfflineJobStore` 协议、`new_offline_job()` 工厂 |
| `mind/offline/service.py` | 维护服务层 | 完整，`reflect_episode` 和 `promote_schema` 两种 job 均有处理逻辑 |
| `mind/offline/worker.py` | 单进程 worker | 完整，claim-process-complete/fail 生命周期闭合，支持 job kind 过滤 |
| `mind/offline/promotion.py` | Promotion 策略 v0 | 完整，包含 4 项准入检查（最少 2 对象、全部 active、跨 episode、无 success/failure 冲突） |
| `mind/offline/replay.py` | Replay 排序与复用指标 | 完整，`select_replay_targets()` + `deterministic_random_decile()` + `future_reuse_rate()` |
| `mind/offline/audit.py` | Evidence / promotion 审计 | 完整，`audit_schema_evidence()` + `audit_promotion_within_window()` |
| `mind/offline/phase_e.py` | Gate 评估器 | 完整，startup + gate + dev eval A/B 路径 |
| `mind/fixtures/long_horizon_dev.py` | `LongHorizonDev v1` fixture | 完整，冻结 30 条序列（20 episode + 10 failure-pair），5 步/条 |
| `mind/kernel/postgres_store.py` | PostgreSQL offline_jobs CRUD | 完整，enqueue / iter / claim / complete / fail 五方法 |
| `mind/kernel/sql_tables.py` | offline_jobs 表定义 | 完整，15 列 + 2 索引 |
| `mind/primitives/service.py` | Schema stability 增强 | 完整，`_supporting_episode_ids()` + `_schema_stability_score()` |
| `alembic/versions/20260309_0004_offline_jobs.py` | 数据库迁移 | 完整，upgrade/downgrade 对称 |
| `mind/cli.py` | CLI 入口 | 完整，新增 `phase_e_startup_main` / `phase_e_gate_main` / `offline_worker_main` |
| `pyproject.toml` | Entry points | 完整，3 个新命令注册 |

### 4.2 测试覆盖

| 测试文件 | 覆盖点 | 通过 |
| --- | --- | --- |
| `test_offline_policy.py` | promotion accept/reject | PASS |
| `test_offline_worker.py` | worker reflect+promote 端到端、failure 标记 | PASS |
| `test_phase_e_startup.py` | `LongHorizonDev v1` 冻结 + startup gate | PASS |
| `test_phase_e_gate.py` | `E-1 ~ E-5` formal gate | PASS |
| `test_postgres_regression.py` | offline_jobs 生命周期 + PostgreSQL Phase E gate（需 DSN） | PASS / skipped |

### 4.3 PostgreSQL claim 路径

`claim_offline_job()` 使用 `FOR UPDATE SKIP LOCKED + pg_try_advisory_xact_lock(hashtext(job_id))` 实现：

- `FOR UPDATE SKIP LOCKED`：避免 worker 间互相等锁
- `pg_try_advisory_xact_lock`：事务级 advisory lock，事务结束自动释放
- priority DESC + available_at ASC + created_at ASC + job_id ASC 排序：确保高优先级且最早可用的 job 被优先消费
- `attempt_count < max_attempts` 过滤：防止无限重试

审查结论：实现正确，无死锁风险，无遗漏边界。

---

## 5. 必要性审查

### 5.1 每个新增模块是否有 Phase E gate 指标驱动

| 模块 | 驱动指标 | 必要性判定 |
| --- | --- | --- |
| `offline/jobs.py` | E-5（离线维护需要 job 抽象） | 必要 |
| `offline/service.py` | E-1, E-5（维护产出必须接入 primitive + trace） | 必要 |
| `offline/worker.py` | E-5（实际执行 job 的调度器） | 必要 |
| `offline/promotion.py` | E-4（promotion 策略直接影响 PromotionPrecision@10） | 必要 |
| `offline/replay.py` | E-3（ReplayLift 实现依赖 replay target ranking） | 必要 |
| `offline/audit.py` | E-2, E-4（SchemaValidationPrecision 和 PromotionPrecision@10 均依赖 audit） | 必要 |
| `offline/phase_e.py` | E-1 ~ E-5（gate 评估器总入口） | 必要 |
| `fixtures/long_horizon_dev.py` | E-3, E-4（LongHorizonDev v1 是 gate 共享工件） | 必要 |
| `kernel/postgres_store.py` 增量 | E-5（PostgreSQL 路径回归需要真实 job queue） | 必要 |
| `kernel/sql_tables.py` 增量 | 同上 | 必要 |
| `primitives/service.py` 增量 | E-2, E-4（schema stability 信号和 supporting_episode_ids 支持 promotion 判定） | 必要 |

### 5.2 无冗余代码

未发现无用导入、死代码分支或未使用的公共 API。`_utc_now()` 在 `jobs.py`、`service.py`、`worker.py` 各存在一份，虽有轻微重复但均为内部使用，不构成实际问题。

---

## 6. 合理性审查

### 6.1 promotion policy v0

当前 promotion 准入标准：

1. 至少 2 个 source 对象
2. 全部 source 为 active 状态
3. 来自 >= 2 个不同 episode
4. 不含 success + failure 冲突反思

审查结论：准入标准合理，保守但不过度。v0 不做语义深度匹配是正确的渐进策略——先冻结结构化 gate，再在 Phase F/G 加入更复杂判断。

### 6.2 stability_score 公式

`min(0.95, 0.45 + 0.10 * len(target_objects) + 0.10 * len(supporting_episode_ids))`

- 2 对象 2 episode → 0.85
- 3 对象 3 episode → 0.95（cap）

审查结论：公式合理。`PrimitiveService._schema_stability_score()` 与 `promotion.py` 的 `assess_schema_promotion()` 使用相同公式，保持一致性。

### 6.3 LongHorizonDev v1 fixture 设计

- 20 条 episode 序列（1:1 映射 GoldenEpisodeSet v1 的 20 个 episode）
- 10 条 failure-pair 序列（C(5,2) = 10，来自 5 个 failure episode 的两两组合）
- 每条序列 5 步
- failure-pair 序列包含 `promotion_target_refs`

审查结论：fixture 结构合理。30 条序列满足 phase_gates.md 要求的 `>= 30`，步数 5 满足 `5~10` 范围。通过 `_build_failure_pair_sequence()` 函数自动从 failure episode 组合生成跨 episode 样本，避免手工标注偏差。

### 6.4 replay_score 排序函数

- ReflectionNote: +0.70（failure 额外 +0.25）
- SummaryNote: +0.45
- SchemaNote: +0.40
- TaskEpisode: +0.10
- RawRecord: -0.05
- stale-memory claim: +0.10

审查结论：权重设计合理（反思 > 总结 > schema > episode > raw），failure reflection 获得最高优先级符合"从失败中学习"的离线维护目标。

### 6.5 PUS A/B dev eval 设计

- baseline（no-maintenance）：只使用原始 candidate pool，无 promotion schema
- treatment（maintenance）：candidate pool 加入 promoted schema，greedy handle 选择时 `prefer_future_coverage=True`

审查结论：对比设计清晰。两条路径共享同一套 PUS 公式，maintenance 路径的改进主要来自 promotion schema 的压缩复用效果，而不是阈值放宽。`pus_improvement=0.14` 和 `pollution_rate_delta=0.00` 说明当前实现在不引入污染的前提下取得了显著收益。

### 6.6 evidence audit 机制

`audit_schema_evidence()` 通过 token overlap 检验 schema 的 rule 文本和 evidence ref 对象之间的语义关联：

- 排除停用词（a, and, from, objects, pattern, promote, repeated, support 等）
- 对每个 evidence ref 检查是否有非停用词的 token 交集

审查结论：作为 v0 级别的证据检验，token overlap 方案简单但有效。在当前冻结样例驱动的评估框架下，这个精度足够。后续 Phase F 可考虑引入更复杂的语义匹配。

---

## 7. 文档噪声排查

### 7.1 已修复项

| 文件 | 问题 | 修复 |
| --- | --- | --- |
| `scripts/run_postgres_regression.py` | docstring 仍为 "Phase B/C regression" | 修改为 "Phase B/C/D/E regression" |
| `tests/test_postgres_regression.py` | docstring 仍为 "Phase B/C gates" | 修改为 "Phase B/C/D/E gates" |

### 7.2 确认无问题的文档

| 文件 | 审查结果 |
| --- | --- |
| `README.md` | Phase E 相关内容已正确补入，状态说明已更新为 Phase E |
| `docs/README.md` | Phase E 启动清单和验收报告已添加到索引，查询入口已更新 |
| `docs/foundation/phase_gates.md` | Phase E gate 定义完整，无过时内容 |
| `docs/foundation/implementation_stack.md` | Phase E 当前状态段落已补入，无冲突 |
| `docs/design/phase_e_startup_checklist.md` | 启动清单正确标注为历史记录（非当前口径），指向验收报告 |
| `docs/reports/phase_e_acceptance_report.md` | E-1 ~ E-5 结果与实际运行输出匹配，无篡改 |
| `docs/design/design_breakdown.md` | 无 Phase E 相关噪声 |
| `docs/design/phase_c_startup_checklist.md` | 无 Phase E 相关噪声 |
| `docs/reports/phase_d_acceptance_report.md` | 历史报告，无需修改 |
| `docs/reports/phase_d_independent_audit.md` | 历史报告，无需修改 |
| `docs/reports/phase_d_smoke_report.md` | 历史报告，无需修改 |
| `docs/reports/postgres_store_audit.md` | 审核范围仍标为 "Phase B/C"，但这是该次审核的真实范围，不属于噪声 |

### 7.3 确认无噪声的搜索

- `docs/` 全量 `TODO / FIXME / TBD` 扫描：仅在 `phase_a_acceptance_report.md` 和 `phase_gates.md` 中出现，均为引用 A-4 的检查方法论文本，不是实际未解决项
- Phase E 相关文档链接：`phase_e_startup_checklist.md`、`phase_e_acceptance_report.md` 均已被正确索引

---

## 8. 观察项（低风险，非阻断）

### 8.1 PostgreSQL 集成未在本轮实际执行

当前环境未提供 `MIND_TEST_POSTGRES_DSN`，因此 `test_postgres_regression.py` 中的 3 个 PostgreSQL Phase E 测试（`test_postgres_offline_job_lifecycle`、`test_postgres_phase_e_gate`）被 skip。代码路径已审阅确认正确，但未获得实测验证。

建议：在下一次有 DSN 的环境中补跑。

### 8.2 `_utc_now()` 存在轻微重复

`jobs.py`、`service.py`、`worker.py` 各自定义了 `_utc_now()` 或 `utc_now()`。虽然不影响功能，但统一到 `jobs.py` 的 `utc_now()` 可减少未来维护成本。

建议：Phase F 时统一。

---

## 9. 最终判定

| 维度 | 结论 |
| --- | --- |
| 框架设计完整性 | PASS — E-1 ~ E-5 与 phase_gates.md 完全对齐 |
| 实现完整性 | PASS — 15 个文件职责明确，测试覆盖充分 |
| 必要性 | PASS — 每个模块均有明确的 gate 指标驱动，无冗余 |
| 合理性 | PASS — 策略保守渐进，公式正确，fixture 设计合理 |
| 文档噪声 | PASS — 2 处过时 docstring 已修复，无其他噪声 |

**Phase E 独立审计总结论：PASS**
