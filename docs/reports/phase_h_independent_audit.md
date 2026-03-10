# Phase H 独立审计报告

**审计阶段**: Phase H — Provenance Foundation  
**审计时间**: 2026-03-10  
**审计者**: Independent Audit Agent (Turn 9)  
**前序审计**: Phase D (`phase_d_independent_audit.md`), Phase G (`phase_g_independent_audit.md`)

---

## 1. 审计范围

Phase H 实现了 **Provenance Foundation**（溯源基础），包含三个核心子系统：

| 子系统 | 描述 |
|--------|------|
| Direct Provenance | 每条 RawRecord/ImportedRawRecord 绑定唯一的直接溯源记录 |
| Governance Control Plane | plan → preview → execute 三阶段隐匿治理流程 |
| Concealment Isolation | 隐匿对象在读取、检索、工作区、回放、离线维护、排名中完全不可见 |

**Phase H Gate 规格** (H-1 ~ H-8) 定义于 `docs/foundation/phase_gates.md` L737-771。

---

## 2. 审计文件清单

### 2.1 新增文件

| 文件 | 行数 | 职责 |
|------|------|------|
| `mind/kernel/provenance.py` | 159 | ProducerKind/SourceChannel/RetentionClass 枚举、DirectProvenanceInput/Record/Summary 模型、build 函数 |
| `mind/kernel/governance.py` | 173 | GovernanceAction/Stage/Capability/Scope/Outcome 枚举、ConcealSelector（Pydantic 验证器）、GovernanceAuditRecord（合约验证器） |
| `mind/governance/__init__.py` | 18 | 包级导出 |
| `mind/governance/service.py` | 313 | GovernanceService：plan_conceal / preview_conceal / execute_conceal；_resolve_selector 多字段匹配 |
| `mind/governance/phase_h.py` | 605 | PhaseHGateResult（h1~h8 计算属性）、evaluate_phase_h_gate、assert_phase_h_gate、_ranking_isolation_regression |
| `alembic/versions/20260310_0005_provenance_ledger.py` | 45 | PostgreSQL provenance_ledger 表迁移 |
| `alembic/versions/20260310_0006_governance_audit.py` | 42 | PostgreSQL governance_audit 表迁移（JSONB） |
| `alembic/versions/20260310_0007_concealed_objects.py` | 33 | PostgreSQL concealed_objects 表迁移 |
| `scripts/run_phase_h_gate.py` | 21 | Phase H gate 运行脚本 |
| `tests/test_phase_h_gate.py` | 37 | 2 tests — gate 通过 + JSON report |
| `tests/test_governance_service.py` | 200 | 3 tests — 完整流程 + execute 需 preview + plan 需 capability |
| `tests/test_concealment_online.py` | 76 | 1 test — read/retrieve/workspace 隐匿隔离 |
| `tests/test_concealment_offline.py` | 85 | 2 tests — replay 排除隐匿 + replay_targets 跳过隐匿 |
| `tests/test_governance_audit.py` | 117 | 2 tests — round-trip + approval 合约验证 |

### 2.2 修改文件

| 文件 | 主要变更 |
|------|----------|
| `mind/kernel/store.py` | MemoryStore Protocol +13 新方法；SQLiteMemoryStore 3 新表 + CRUD + concealment 过滤（iter_latest_objects、search_objects、raw_records_for_episode） |
| `mind/kernel/postgres_store.py` | PostgresMemoryStore +13 新方法；_latest_objects_subquery LEFT JOIN 隐匿过滤；Transaction 完整接线 |
| `mind/kernel/sql_tables.py` | 3 新 PostgreSQL 表定义 + 索引 |
| `mind/primitives/contracts.py` | Capability 枚举(5)、CAPABILITY_REQUIRED 错误码、direct_provenance/include_provenance/provenance_summaries 字段 |
| `mind/primitives/service.py` | write_raw 创建溯源记录；read 检查隐匿+能力；read_with_provenance 便捷方法；retrieve 需 MEMORY_READ |
| `mind/primitives/runtime.py` | .model_dump(mode="json")、_json_compatible_payload 辅助函数 |
| `mind/workspace/builder.py` | _is_object_concealed 防御性检查 |
| `mind/offline/replay.py` | select_replay_targets 跳过隐匿对象 |
| `tests/test_phase_c_primitives.py` | +7 tests（Phase H 溯源/能力覆盖） |
| `tests/test_postgres_regression.py` | +4 tests（Phase H PostgreSQL 回归） |
| `mind/cli.py` | phase_h_gate_main 入口函数 |
| `pyproject.toml` | **修复后**：新增 mind-phase-h-gate 脚本入口 |

---

## 3. 缺陷发现与修复

### DEF-1: pyproject.toml 缺少 mind-phase-h-gate 脚本入口 (Medium)

**发现**: `mind/cli.py` 中定义了 `phase_h_gate_main`、`scripts/run_phase_h_gate.py` 存在，但 `pyproject.toml` 的 `[project.scripts]` 中没有 `mind-phase-h-gate` 条目。所有前序阶段 (B~G) 均已注册。

**影响**: `pip install -e .` 后无法通过 `mind-phase-h-gate` 命令直接运行 Phase H gate，与其他阶段不一致。

**修复**: 在 `pyproject.toml` 第 38 行后添加：
```toml
mind-phase-h-gate = "mind.cli:phase_h_gate_main"
```

**验证**: 新增 `test_pyproject_contains_phase_h_gate_entry` 回归测试。

---

## 4. 多维度审计结论

### 4.1 必要性

| 审查点 | 结论 |
|--------|------|
| Direct Provenance 是否为 Phase I (Runtime Access Modes) 前置依赖 | ✅ 是——Phase I 需要溯源信息来区分运行时访问级别 |
| Governance Control Plane 是否必要 | ✅ 是——隐匿/擦除操作需要审计链确保可追溯 |
| Concealment Isolation 是否必要 | ✅ 是——隐匿对象必须在所有读路径消失，Phase H gate 明确要求 |
| 无多余代码 | ✅ 审核未发现死代码或未使用的导出 |

### 4.2 完整性

| 审查点 | 结论 |
|--------|------|
| H-1 direct provenance binding | ✅ write_raw 自动创建溯源记录，100% 绑定 |
| H-2 authoritative provenance integrity | ✅ UNIQUE 约束防重复；对象存在性+类型校验防孤儿 |
| H-3 low-privilege provenance isolation | ✅ include_provenance=True 需 MEMORY_READ_WITH_PROVENANCE |
| H-4 privileged summary convergence | ✅ ProvenanceSummary 结构性排除 6 个高敏字段 |
| H-5 conceal online isolation | ✅ read/retrieve/workspace 三路径均过滤隐匿对象 |
| H-6 conceal offline isolation | ✅ replay/maintenance/replay_targets 三路径均排除隐匿 |
| H-7 governance audit chain | ✅ plan→preview→execute 三阶段审计记录完整 |
| H-8 provenance optimization leak | ✅ RESERVED_CONTROL_PLANE_METADATA_FIELDS + strip 确保溯源不进入检索/排名 |
| SQLite ↔ PostgreSQL 对等性 | ✅ _write_direct_provenance 验证逻辑完全一致；_latest_objects_subquery 使用 LEFT JOIN + WHERE IS NULL |
| Alembic 迁移链 | ✅ 0004→0005→0006→0007 连续无断裂 |
| UNIQUE(object_id) on concealed_objects | ✅ SQLite DDL + sql_tables.py + Alembic 三处一致 |

### 4.3 合理性

| 审查点 | 结论 |
|--------|------|
| ConcealSelector Pydantic 验证器防空选择器 | ✅ `require_at_least_one_filter` + `enforce_time_window` |
| GovernanceAuditRecord 合约验证器 | ✅ approve 仅限 erase+full 组合；stage→capability 映射正确 |
| execute_conceal 幂等性 | ✅ 已隐匿对象进入 already_concealed_object_ids，不触发 UNIQUE 冲突 |
| `_is_object_concealed` 防御性 getattr 模式 | ✅ 合理——兼容未实现隐匿方法的旧 store 实现 |
| ProducerKind(6) / SourceChannel(5) / RetentionClass(4) 枚举覆盖 | ✅ 合理，覆盖主要场景 |
| Capability 枚举(5) 粒度 | ✅ 与 Phase H 需求匹配，approve 预留 Phase I+ |
| _ranking_isolation_regression 覆盖 search_text + embedding_text + object_embedding + keyword 搜索 | ✅ 四维度隔离验证 |

### 4.4 DRY / 代码质量

| 审查点 | 结论 |
|--------|------|
| SQLite/PostgreSQL 写入重复 | ⚠️ 观察——两套 store 的 provenance/governance/concealment 写入逻辑高度相似但尚未合并。当前阶段可接受，建议后续考虑公共基类提取 |
| `_is_object_concealed` 在 service.py 和 builder.py 中重复 | ⚠️ 观察——同一功能两处独立实现。当前防御性设计合理，但可考虑提取到工具模块 |

---

## 5. 补充测试

审计新增 **9 个测试**（`tests/test_phase_h_deep_audit.py`）：

| 测试 | 覆盖目标 |
|------|----------|
| `test_pyproject_contains_phase_h_gate_entry` | DEF-1 回归验证 |
| `test_duplicate_direct_provenance_for_same_object_rejected` | H-2 完整性——重复溯源写入被拒 |
| `test_conceal_selector_rejects_empty_filter` | ConcealSelector 验证器边界 |
| `test_double_execute_reports_already_concealed` | execute_conceal 幂等性 |
| `test_preview_without_plan_rejected` | 治理流程顺序约束 |
| `test_provenance_for_missing_object_rejected` | 溯源绑定到不存在对象被拒 |
| `test_provenance_summary_excludes_all_high_sensitivity_fields` | ProvenanceSummary 结构隔离合约 |
| `test_build_provenance_summary_strips_high_sensitivity` | build_provenance_summary 运行时隔离 |
| `test_approve_stage_valid_only_with_erase_full` | GovernanceAuditRecord approve 合约 |

---

## 6. 验证结果

| 检查项 | 结果 |
|--------|------|
| `ruff check` | ✅ All checks passed |
| `mypy` | ✅ 98 source files, no issues |
| `pytest` | ✅ **153 passed**, 11 skipped (新增 9 tests) |
| Phase H gate (H-1~H-8) | ✅ 全部 PASS |
| Phase B gate (B-1~B-5) | ✅ PASS — 无回归 |
| Phase G gate (G-1~G-5) | ✅ PASS — 无回归 |

---

## 7. Phase I 就绪评估

| 就绪条件 | 状态 |
|----------|------|
| H-1~H-8 全部通过 | ✅ |
| 前序 gate 无回归 (B, G) | ✅ |
| 溯源基础层完整（ledger + summary + isolation） | ✅ |
| 治理控制平面就绪（plan/preview/execute 三阶段） | ✅ |
| 隐匿隔离覆盖在线 + 离线所有路径 | ✅ |
| PostgreSQL 对等实现 + Alembic 迁移链完整 | ✅ |
| CLI 入口注册 | ✅（DEF-1 已修复） |
| 能力模型（Capability 枚举）为 Phase I Runtime Access Modes 提供基础 | ✅ |

**结论**: Phase H 实现完整且合理，已修复 1 个缺陷（DEF-1），新增 9 个补充测试。**可以进入 Phase I**。

---

## 8. 变更摘要

| 变更 | 文件 | 类型 |
|------|------|------|
| DEF-1 修复 | `pyproject.toml` | 缺陷修复 |
| 补充审计测试 | `tests/test_phase_h_deep_audit.py` | 新增 9 tests |
