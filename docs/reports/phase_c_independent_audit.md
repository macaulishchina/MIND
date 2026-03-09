# Phase C 独立审计报告

审计日期：`2026-03-09`

审计人：独立审计（非原开发者）

审计范围：

- 本次审计覆盖 Phase C 从"准备完毕"推进到"primitive 开始可用"的全部未提交变更
- 新增文件：[service.py](../../mind/primitives/service.py)、[test_phase_c_primitives.py](../../tests/test_phase_c_primitives.py)、[test_phase_c_validation.py](../../tests/test_phase_c_validation.py)
- 修改文件：[contracts.py](../../mind/primitives/contracts.py)、[runtime.py](../../mind/primitives/runtime.py)、[primitives/\_\_init\_\_.py](../../mind/primitives/__init__.py)、[schema.py](../../mind/kernel/schema.py)、[integrity.py](../../mind/kernel/integrity.py)、[store.py](../../mind/kernel/store.py)、[kernel/\_\_init\_\_.py](../../mind/kernel/__init__.py)

相关文档：

- 规范定义见 [spec.md](../foundation/spec.md)
- 阶段 gate 见 [phase_gates.md](../foundation/phase_gates.md)
- Phase C 启动清单见 [phase_c_startup_checklist.md](../design/phase_c_startup_checklist.md)
- Phase B 独立审计见 [phase_b_independent_audit.md](./phase_b_independent_audit.md)

---

## 0. 总结论

**Phase C "primitive 开始可用" 独立审计结论：`PASS`**

7/7 primitives 已可调用，结构化日志、预算约束、失败原子性三大支柱已具备。
Phase C 启动清单 P0 全部完成，P1 大部分完成，剩余量化门槛（C-2 200/200、C-4 50/50、C-5 50/50）需在 `PrimitiveGoldenCalls v1` 建立后逐步收敛。

独立审计发现 **3 项缺陷**和 **7 项观察**。3 项缺陷均已在审计后立即修复并通过回归测试验证（20/20 测试通过，Phase B gate PASS，ruff/mypy 全部通过）。

---

## 1. 审计方法

本次审计从以下独立操作出发：

1. **差异收集**：通过 `git diff` / `git status` 收集全部未提交变更
2. **代码通读**：逐文件阅读所有新增和修改的模块，建立独立理解
3. **测试复现**：运行 `python3 -m pytest tests/ -v`，确认 `20/20` 通过
4. **工具链验证**：运行 `ruff check .`（全部通过）、`mypy mind tests scripts`（全部通过）
5. **Phase B 回归**：运行 `python3 scripts/run_phase_b_gate.py`，确认 B-1 ~ B-5 全部 PASS，无回归
6. **深度审计**：逐 primitive 审查合约合规性、对象构造完整性、事务原子性、预算执行正确性、错误码一致性
7. **Cross-reference**：与 Phase C 启动清单、spec、phase gates 交叉验证

---

## 2. 基线验证结果

| 验证项 | 结果 |
| --- | --- |
| pytest 20/20 | ✅ 全部通过（1.30s） |
| ruff check | ✅ All checks passed |
| mypy strict | ✅ Success: no issues found in 19 source files |
| Phase B gate B-1 ~ B-5 | ✅ 全部 PASS，无回归 |
| round-trip 142/142 | ✅ |
| replay 20/20 | ✅ |
| source_trace_coverage 1.00 | ✅ |
| metadata_coverage 1.00 | ✅ |
| dangling_refs / cycles / version_chain_issues | 0 / 0 / 0 ✅ |

---

## 3. Phase C Gate 当前进度

| Gate | 指标 | 阈值 | 当前状态 | 说明 |
| --- | --- | --- | --- | --- |
| C-1 | Primitive 实现覆盖 | 7/7 可调用 | ✅ 7/7 | `test_all_seven_primitives_are_callable_and_logged` 验证 |
| C-2 | 请求/响应 schema 合规率 | 200/200 | ⚠️ 7/7 | typed schema 已冻结，`PrimitiveGoldenCalls v1` 未建立 |
| C-3 | 结构化日志覆盖率 | 100% | ✅ 7/7 | 每次调用均有 `actor / timestamp / target_ids / cost / outcome` |
| C-4 | 预算约束执行率 | 50/50 | ⚠️ 1/1 | 机制已验证，量化样例未达标 |
| C-5 | 失败原子性 | 50/50 | ⚠️ 1/1 | 机制已验证，量化样例未达标 |

**结论**：C-1、C-3 已满足最终阈值。C-2、C-4、C-5 的机制和架构已就位，量化覆盖需在后续 `PrimitiveGoldenCalls v1` 中补齐。

---

## 4. 发现的缺陷

### 缺陷 C-I-1：`PrimitiveCallLog` 未从 `mind.primitives` 包级别导出 — ✅ 已修复

**严重程度**：低

**现象**：

`PrimitiveCallLog` 是核心合约类型，在 `contracts.py` 中定义，但 `mind/primitives/__init__.py` 的 `from .contracts import (...)` 和 `__all__` 列表中均遗漏了 `PrimitiveCallLog`。消费者必须使用 `from mind.primitives.contracts import PrimitiveCallLog` 才能访问，与其他合约类型的导入方式不一致。

**修复**：

在 `mind/primitives/__init__.py` 的 `from .contracts import (...)` 和 `__all__` 列表中补充 `PrimitiveCallLog`。

---

### 缺陷 C-I-2：`store.py` 与 `contracts.py` 之间存在循环导入 — ✅ 已修复

**严重程度**：中

**现象**：

`mind/kernel/store.py` 在模块顶层执行 `from mind.primitives.contracts import BudgetEvent, PrimitiveCallLog`。当以 `from mind.primitives import ...` 方式导入（触发 `mind/primitives/__init__.py`）时，形成循环导入链：

```
mind.primitives.__init__
  → .contracts
    → mind.kernel.schema
      → (触发 mind.kernel.__init__)
        → .store
          → mind.primitives.contracts (循环！)
```

导致 `ImportError: cannot import name 'BudgetEvent' from partially initialized module`。

测试未暴露此问题，因为测试文件恰好先导入了 `mind.kernel` 子模块（通过 `mind.fixtures.golden_episode_set` → `mind.kernel.replay`），使得 `mind.kernel.__init__` 在循环触发前已完成初始化。

**根因**：

循环发生在 `mind.kernel.__init__` 被触发时——它 eager-import 了 `.store`，而 `.store` 又依赖 `mind.primitives.contracts`。但整个代码库中没有任何模块使用 `from mind.kernel import ...` 的包级别导入，所有消费者都直接导入子模块（`from mind.kernel.store import ...`），`__init__.py` 中的 eager re-export 完全多余。

**修复**：

将 `mind/kernel/__init__.py` 清理为仅保留 docstring，移除所有 eager re-export。`store.py` 保持干净的顶层 `from mind.primitives.contracts import BudgetEvent, PrimitiveCallLog` 不变。

---

### 缺陷 C-I-3：`service.py` `_link` 方法关闭括号缩进不一致 — ✅ 已修复

**严重程度**：低（风格一致性）

**现象**：

`_link` 方法签名的关闭括号与参数同级缩进（8 空格），而其他 6 个私有方法均使用与 `def` 同级缩进（4 空格）：

```python
# _link（修复前）—— 不一致
    def _link(
        self,
        request: LinkRequest,
        context: PrimitiveExecutionContext,
        transaction: PrimitiveTransaction,
        ) -> PrimitiveHandlerResult[LinkResponse]:  # ← 8 空格

# 其他方法（一致风格）
    def _write_raw(
        self,
        request: WriteRawRequest,
        context: PrimitiveExecutionContext,
        transaction: PrimitiveTransaction,
    ) -> PrimitiveHandlerResult[WriteRawResponse]:  # ← 4 空格
```

ruff 和 mypy 均不报错（两种风格在 PEP 8 中均合法），但在同一文件中不一致影响可读性。

**修复**：

将 `_link` 的关闭括号缩进统一为 4 空格。

---

## 5. 修复后回归验证

| 验证项 | 结果 |
| --- | --- |
| pytest 20/20 | ✅ 通过 |
| ruff check | ✅ All checks passed |
| mypy strict | ✅ no issues found in 19 source files |
| Phase B gate | ✅ B-1 ~ B-5 全部 PASS |
| `from mind.primitives import PrimitiveCallLog` | ✅ 不再报循环导入 |

---

## 6. 各文件审计详情

### 6.1 `mind/primitives/service.py`（新增，943 行）

**职责**：Phase C 的 7/7 primitive 实现，library-first service object 形态。

**审计结论**：✅ 合格

**正面发现**：

- 7 个 public 方法统一模式：`model_validate(context)` → 闭包 handler → `execute_read()` / `execute_write()`，模式一致且清晰
- 每个 primitive 创建的对象均包含 spec §2.3 规定的 10 个必填字段
- 每个对象的 `metadata` 均覆盖 spec §2.5 规定的类型特定必填字段：
  - `RawRecord`: `record_kind`, `episode_id`, `timestamp_order` ✅
  - `SummaryNote`: `summary_scope`, `input_refs`, `compression_ratio_estimate` ✅
  - `LinkEdge`: `confidence`, `evidence_refs` ✅
  - `ReflectionNote`: `episode_id`, `reflection_kind`, `claims` ✅
  - `SchemaNote`: `kind`, `evidence_refs`, `stability_score`, `promotion_source_refs` ✅
- self-link 检查从 `LinkRequest` model_validator 迁移到 `_link()` 服务层 — 合理，model_validator 不应承担业务逻辑
- 状态转换守卫完备：`archive` 要求 `active`、`deprecate` 要求 `active/archived`、`reprioritize` 排除 `invalid`
- `_enforce_budget` 使用 `min(context_limit, request_limit)` — 双层限额取严值 ✅
- 失败路径全部使用 `PrimitiveRejectedError`，由 runtime 统一捕获并回滚 ✅

**观察**：

- `_summarize_text` 仅取前 24 词作为摘要占位 — 可接受，Phase E 接入 LLM 前的最小实现
- `_enforce_budget` 每次调用遍历全部 `budget_events` 表 — O(N) 扫描，Phase C 数据量下无影响，Phase D 后需索引优化
- `_retrieve` 的 `_latest_objects(store.iter_objects())` 加载全表到内存 — 同上

### 6.2 `mind/primitives/contracts.py`（修改）

**变更**：新增 `PrimitiveExecutionContext` 模型；移除 `LinkRequest.reject_self_links` model_validator

**审计结论**：✅ 合格

- `PrimitiveExecutionContext` 字段设计合理：`actor`（必填）、`budget_scope_id`（默认 `"global"`）、`budget_limit`（可选）
- 移除 `reject_self_links` validator 后，self-link 防护已转移到 `service.py._link()`，防护无缺口
- 所有 20 个 `PrimitiveErrorCode` 枚举值在 `service.py` 中均有对应触发路径
- `PrimitiveCallLog` 的 `enforce_log_shape` validator 与 `PrimitiveExecutionResult.enforce_outcome_shape` 保持对称 ✅

### 6.3 `mind/primitives/runtime.py`（修改）

**变更**：新增 `ValidationError` 捕获处理，`_build_failure_result` 参数类型放宽为 `BaseModel | dict[str, Any]`

**审计结论**：✅ 合格

- `execute_read` 和 `execute_write` 均在请求 schema 校验失败时返回 `FAILURE` + `SCHEMA_INVALID` 错误码 ✅
- `execute_write` 在 `PrimitiveRejectedError` 时返回 `REJECTED`，在其他异常时返回 `ROLLED_BACK` — 语义区分正确
- `execute_write` 的事务内日志和预算事件记录在同一原子事务中 ✅
- `_schema_error` 使用 `exc.errors(include_url=False)` 避免泄漏内部 URL ✅

### 6.4 `mind/kernel/schema.py`（修改）

**变更**：新增 6 项 typed validation

**审计结论**：✅ 合格

新增验证均与 Phase B 独立审计建议 O-4、O-6 一致：

| 验证项 | spec 依据 | 测试覆盖 |
| --- | --- | --- |
| `LinkEdge.confidence` ∈ [0, 1] | §2.5 LinkEdge | `test_entity_alias_and_link_confidence_are_typed` |
| `WorkspaceView.slot_limit` ≥ 1 | §4.5 | `test_workspace_view_rejects_slot_count_above_limit` |
| `WorkspaceView slot_count ≤ slot_limit` | §4.5 | 同上 |
| `SchemaNote.stability_score` ∈ [0, 1] | §2.5 SchemaNote | schema validator 内部验证 |
| `EntityNode.alias` 必须为非空字符串列表 | §2.5 EntityNode | `test_entity_alias_and_link_confidence_are_typed` |
| slot `source_refs` / `evidence_refs` 非空 | §4.5 slot traceability | `_validate_slot` 内部验证 |

### 6.5 `mind/kernel/integrity.py`（修改）

**变更**：新增 `LinkEdge.content.src_id/dst_id` 存在性检查

**审计结论**：✅ 合格

- 响应 Phase B 独立审计建议 O-2
- 实现正确：遍历 `LinkEdge` 类型对象，检查 `content` dict 中 `src_id` 和 `dst_id` 是否存在于 `object_ids` 集合中
- 测试 `test_integrity_report_flags_missing_link_endpoints` 验证了断裂引用被正确标记 ✅

### 6.6 `mind/kernel/store.py`（修改）

**变更**：无功能变更，循环导入修复涉及此文件

**审计结论**：✅ 合格

- 顶层 `from mind.primitives.contracts import BudgetEvent, PrimitiveCallLog` 保持干净
- 循环导入通过清理 `kernel/__init__.py` 解决，`store.py` 无需做任何妥协

### 6.7 `mind/kernel/__init__.py`（修改）

**变更**：移除所有 eager re-export，仅保留 docstring

**审计结论**：✅ 合格

- 整个代码库中没有 `from mind.kernel import ...` 的使用方，所有消费者均直接导入子模块
- 移除 eager re-export 后消除了循环导入的根因，无需在 `store.py` 中引入延迟导入等 workaround

### 6.8 测试文件

#### `tests/test_phase_c_primitives.py`（新增，204 行）

| 测试 | 覆盖目标 | 审计结论 |
| --- | --- | --- |
| `test_all_seven_primitives_are_callable_and_logged` | C-1（7/7 可调用）、C-3（日志覆盖） | ✅ 验证所有 primitive 返回 SUCCESS、7 条 log、7 条 budget event |
| `test_budget_rejection_returns_explicit_error_code` | C-4（预算拒绝） | ✅ 紧预算 → REJECTED + BUDGET_EXHAUSTED |
| `test_reorganize_simple_rollback_keeps_store_atomic` | C-5（失败原子性） | ✅ 已归档对象再归档 → REJECTED、无 partial write（版本号不变） |

#### `tests/test_phase_c_validation.py`（新增，58 行）

| 测试 | 覆盖目标 | 审计结论 |
| --- | --- | --- |
| `test_workspace_view_rejects_slot_count_above_limit` | schema P1 | ✅ slot 超限被拒 |
| `test_entity_alias_and_link_confidence_are_typed` | schema P1 | ✅ 空别名 + confidence > 1 被拒 |
| `test_integrity_report_flags_missing_link_endpoints` | integrity P1 | ✅ 断裂 LinkEdge src_id 被标记 |

---

## 7. 观察项

### O-C-1：`_enforce_budget` 全表扫描

`_enforce_budget` 每次调用 `self.store.iter_budget_events()`，遍历全部 budget event 表后在 Python 侧按 `scope_id` 过滤。Phase C 数据量极小，无实际影响。Phase D 及以后需要 SQL 级 `WHERE scope_id = ?` + 索引。

### O-C-2：`_summarize_text` 为占位实现

当前实现仅取前 24 词，compression_ratio_estimate 基于字符长度比。语义上不构成真正的摘要。Phase E 接入 LLM 前的最小实现，可接受。

### O-C-3：`_retrieve` 全表加载

`_latest_objects(store.iter_objects())` 在每次 retrieve 调用时加载全部对象到内存。与 Phase B 审计 O-3 (`raw_records_for_episode` 全表扫描) 同源。Phase D 检索阶段需 SQL 级检索。

### O-C-4：`PrimitiveGoldenCalls v1` 尚未建立

Phase C gate C-2（200/200）、C-4（50/50）、C-5（50/50）要求的量化样例集尚未建立。当前仅有 7+1+1 = 9 条 primitive 调用的测试覆盖。建议尽快建立 golden calls 数据集。

### O-C-5：时间一致性校验仍未执行化

Phase B 审计 O-5 指出 `created_at <= updated_at` 和 `version=1` 时两者相等的规则未强制。当前 primitive 实现中 version=1 对象的 `created_at == updated_at`（自动生成），但 schema validator 仍不防护外部构造的不一致对象。

### O-C-6：`PrimitiveService` 未从包级别导出

`PrimitiveService` 需通过 `from mind.primitives.service import PrimitiveService` 导入，未在 `mind/primitives/__init__.py` 中导出。这是有意的设计（合约类型与服务实现分离），但应在文档中明确说明导入路径。

### O-C-7：GoldenEpisodeSet v1 仍仅覆盖 4/8 对象类型

Phase B 审计 O-1 指出的问题。当前 primitive 实现扩展了对象类型的运行时覆盖（LinkEdge、SchemaNote 由 `link` / `reorganize_simple` 产出），但 GoldenEpisodeSet 本身未更新。

---

## 8. Phase C 启动清单交叉验证

### P0 完成度：✅ 5/5

| P0 项 | 状态 | 验证 |
| --- | --- | --- |
| 工程骨架收敛 | ✅ | `pyproject.toml` / `uv` / `pytest` / `ruff` / `mypy` 统一 |
| Primitive contract 模型化 | ✅ | 7 对 request/response schema + 错误码 + 预算模型 |
| Primitive 执行边界 | ✅ | `PrimitiveService` library-first，读/写分离 |
| 事务边界设计 | ✅ | `PrimitiveTransaction` Protocol + `execute_write` 事务包装 |
| 结构化日志 contract | ✅ | `PrimitiveCallLog` 含 `actor/timestamp/target_ids/cost/outcome` |

### P1 完成度：⚠️ 4/5

| P1 项 | 状态 | 验证 |
| --- | --- | --- |
| metadata typed validation 增强 | ✅ | `EntityNode.alias`、`SchemaNote.stability_score`、`WorkspaceView.slot_limit`、`LinkEdge.confidence` |
| integrity 审计扩展 | ✅ | `LinkEdge.content.src_id/dst_id` 存在性检查 |
| WorkspaceView validator 增强 | ✅ | `slot_count <= slot_limit` + slot traceability |
| PrimitiveGoldenCalls v1 | ⬜ | 未建立 |
| 对象覆盖补强 | ✅ | 7 个 primitive 覆盖全部核心对象路径 |

### P2 完成度：⬜ 0/3（预期未开始）

---

## 9. Phase B 审计建议回顾

| Phase B 审计观察 | 本次处理状态 |
| --- | --- |
| O-1：GoldenEpisodeSet 类型覆盖 | ⬜ 延后 → O-C-7 |
| O-2：LinkEdge content 引用审计 | ✅ 已修复（integrity.py） |
| O-3：raw_records_for_episode 全表扫描 | ⬜ 延后 → O-C-3 |
| O-4：slot_limit 校验 | ✅ 已修复（schema.py） |
| O-5：时间一致性校验 | ⬜ 延后 → O-C-5 |
| O-6：metadata 值类型校验 | ✅ 已修复（schema.py） |
| O-7：content 非空校验 | ⬜ 低优先级延后 |
| O-8：priority 边界（正面） | ✅ 确认仍有效 |

---

## 10. 下一步建议

| 优先级 | 建议项 | 原因 |
| --- | --- | --- |
| 高 | 建立 `PrimitiveGoldenCalls v1` (≥ 200 条) | C-2 / C-4 / C-5 量化阈值需要该数据集 |
| 高 | 补充 fault injection 测试 (≥ 50 场景) | C-4 / C-5 50/50 要求 |
| 中 | `_enforce_budget` 改为 SQL 级 `WHERE scope_id = ?` | 性能债，Phase D 前完成 |
| 中 | 执行化 `created_at <= updated_at` 时间一致性 | O-C-5 |
| 中 | 扩展 GoldenEpisodeSet 覆盖 8/8 对象类型 | O-C-7 |
| 低 | `raw_records_for_episode` SQL 级过滤 | O-C-3 |
| 低 | 文档化 `PrimitiveService` 导入路径 | O-C-6 |

---

## 11. 最终结论

**Phase C "primitive 开始可用" 独立审计结论：`PASS`**

- 7/7 primitives 可调用，每个 primitive 产出的对象均满足 spec §2.3 / §2.5 的 schema 要求
- 结构化日志覆盖 100%，每次调用均记录 `actor / timestamp / target_ids / cost / outcome`
- 预算约束机制已验证：超预算调用被拒绝，返回明确 `BUDGET_EXHAUSTED` 错误码
- 失败原子性已验证：事务内的部分写入在异常时被完整回滚
- 发现 3 项缺陷，均已修复并通过回归测试验证（20/20 测试通过，ruff/mypy clean，Phase B gate PASS）
- Phase C 启动清单 P0 全部完成，P1 仅 `PrimitiveGoldenCalls v1` 待建立
- Phase B 独立审计的 8 项观察中，3 项高优已解决，其余按计划延后

**Phase C 已从"准备完毕"成功推进到"primitive 开始可用"。**
