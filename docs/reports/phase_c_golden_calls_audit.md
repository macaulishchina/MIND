# Phase C 独立审计报告：PrimitiveGoldenCalls v1 与 Phase C Smoke Gate

审计日期：`2026-03-09`

审计人：独立审计（非原开发者）

审计范围：

- 本次审计覆盖"做 PrimitiveGoldenCalls v1 和一个 Phase C smoke gate"的全部未提交变更
- 新增文件：[primitive_golden_calls.py](../../mind/fixtures/primitive_golden_calls.py)、[phase_c.py](../../mind/primitives/phase_c.py)、[run_phase_c_gate.py](../../scripts/run_phase_c_gate.py)、[test_phase_c_gate.py](../../tests/test_phase_c_gate.py)、[phase_c_acceptance_report.md](./phase_c_acceptance_report.md)
- 修改文件：[service.py](../../mind/primitives/service.py)、[cli.py](../../mind/cli.py)、[pyproject.toml](../../pyproject.toml)、[README.md](../../README.md)、[docs/README.md](../README.md)、[design_breakdown.md](../design/design_breakdown.md)、[phase_c_startup_checklist.md](../design/phase_c_startup_checklist.md)、[implementation_stack.md](../foundation/implementation_stack.md)、[phase_c_independent_audit.md](./phase_c_independent_audit.md)

相关文档：

- 规范定义见 [spec.md](../foundation/spec.md)
- 阶段 gate 见 [phase_gates.md](../foundation/phase_gates.md)
- Phase C 启动清单见 [phase_c_startup_checklist.md](../design/phase_c_startup_checklist.md)
- 前一轮 Phase C 独立审计见 [phase_c_independent_audit.md](./phase_c_independent_audit.md)

---

## 0. 总结论

**PrimitiveGoldenCalls v1 + Phase C Smoke Gate 独立审计结论：`PASS`**

- 200 条 golden call 固定工件已建立，覆盖正常（60）、异常（40）、超预算（50）、故障回滚（50）四类场景
- Phase C gate（C-1 ~ C-5）已自动化为可重复执行的闭环检查
- gate 与 [phase_gates.md](../foundation/phase_gates.md) 的 C-1 ~ C-5 定义逐条吻合
- 22/22 测试通过，ruff/mypy 全部通过，Phase B gate 无回归

独立审计发现 **0 项缺陷**、**1 项改进**和 **6 项观察**。1 项改进已在审计后修复并通过回归验证。

---

## 1. 审计方法

本次审计遵循以下规则：

- **不以现有实现为起点**：对每个文件从零建立理解，不假设实现正确
- 不仅验证合理性，还独立验证必要性、完毕性和其它角度的合理性

具体操作：

1. **差异收集**：通过 `git diff` / `git status` 收集全部未提交变更
2. **代码通读**：逐文件阅读所有新增和修改的模块
3. **规范交叉验证**：将 golden calls 分布和 gate 判定逻辑与 [phase_gates.md](../foundation/phase_gates.md) C-1 ~ C-5 逐条核对
4. **运行时流程追踪**：完整追踪 `PrimitiveRuntime.execute_write` 和 `execute_read` 的事务与日志路径
5. **测试复现**：运行 `python3 -m pytest -q`，确认 `22/22` 通过
6. **工具链验证**：ruff / mypy 全部通过
7. **Gate 回归**：Phase B gate PASS，Phase C gate PASS

---

## 2. 基线验证结果

| 验证项 | 结果 |
| --- | --- |
| pytest 22/22 | ✅ 通过 |
| ruff check | ✅ All checks passed |
| mypy | ✅ Success: no issues found in 23 source files |
| Phase B gate | ✅ phase_b_gate=PASS |
| Phase C gate | ✅ phase_c_gate=PASS（200/200、7/7、50/50、50/50） |

---

## 3. 合理性审计

### 3.1 架构合理性

| 设计选择 | 审计结论 | 理由 |
| --- | --- | --- |
| golden calls 作为独立 fixture 文件 | ✅ 合理 | 与 gate 评估逻辑解耦，469 行 + 322 行比 791 行单文件更易维护 |
| `dataclass(frozen=True)` 而非 Pydantic | ✅ 合理 | golden call fixtures 是内部测试数据，不需要 Pydantic 的 validation 开销 |
| fault injection 使用方法覆盖而非 monkey-patching | ✅ 合理 | 标准 OOP 继承，不破坏类型检查，比 mock/patch 更可读 |
| 每次调用创建新 PrimitiveService 实例 | ✅ 合理 | 隔离 fault injection 配置，service 是无状态的，无性能代价 |
| `_StepClock` 确定性时钟 | ✅ 合理 | 保证 gate 结果可重复，不依赖系统时间 |
| `_snapshot_objects` + JSON 序列化比对 | ✅ 合理 | `sort_keys=True` 保证确定性，对 rollback 验证充分 |
| `store_factory` 参数化 | ✅ 合理 | 为 Phase D PostgreSQL 迁移预留扩展点 |

### 3.2 Golden Calls 分布合理性

| 类别 | 数量 | 覆盖说明 |
| --- | --- | --- |
| 正常成功 | 60 | 7/7 primitives 均有 smoke 标签（首条），覆盖基本调用路径 |
| 异常拒绝 | 40 | 8 类异常场景 × 5 条，覆盖 NOT_FOUND / INACCESSIBLE / BACKEND_UNAVAILABLE / UNSUPPORTED_SCOPE / SELF_LINK / EVIDENCE_MISSING / EPISODE_MISSING / UNSAFE_STATE_TRANSITION |
| 超预算拒绝 | 50 | 全部 7 个 primitive 均覆盖（round-robin，每个至少 7 次） |
| 故障回滚 | 50 | 5 个写入 primitive 均覆盖（每个 10 次）；read/retrieve 无写入路径，排除正确 |

### 3.3 Gate 与规范映射

| Gate ID | [phase_gates.md](../foundation/phase_gates.md) 定义 | 实现判定逻辑 | 吻合度 |
| --- | --- | --- | --- |
| C-1 | 7/7 primitives 可调用 | `smoke_success_count == 7` | ✅ 精确对应 |
| C-2 | PrimitiveGoldenCalls v1 上 200/200 schema 合规 | `total_calls >= 200 and schema_valid_calls == total_calls` | ✅ 精确对应 |
| C-3 | 100% primitive 调用有 actor/timestamp/target_ids/cost/outcome | `structured_log_calls == total_calls` | ✅ 精确对应 |
| C-4 | 50/50 超预算调用被拒绝且返回明确错误码 | `budget_total == 50 and budget_rejection_match_count == budget_total` | ✅ 精确对应 |
| C-5 | 50/50 注入失败场景无 partial write | `rollback_total == 50 and rollback_atomic_count == rollback_total` | ✅ 精确对应 |

---

## 4. 必要性审计

逐文件审查"是否有多余代码或文件"：

| 文件 | 必要性 | 理由 |
| --- | --- | --- |
| `primitive_golden_calls.py` | ✅ | C-2 要求 200/200 schema 合规，C-4/C-5 要求 50/50 量化样例，必须有固定工件 |
| `phase_c.py` | ✅ | gate 自动化必需；否则 C-1 ~ C-5 只能手动验证 |
| `service.py` `_after_write_operation` hook | ✅ | C-5 fault injection 必需；hook 放在事务内、写后提交前，是唯一干净的注入点 |
| `run_phase_c_gate.py` | ✅ | CLI 脚本入口，与 Phase B 对称 |
| `test_phase_c_gate.py` | ✅ | CI 自动回归必需 |
| `cli.py` `phase_c_gate_main` | ✅ | `uv run mind-phase-c-gate` 入口 |
| `pyproject.toml` entry point | ✅ | 支持 CLI entry point |
| `phase_c_acceptance_report.md` | ✅ | Phase C 正式验收记录 |
| 文档更新（README / 清单 / 技术栈 / 索引） | ✅ | 保持文档与实现同步 |

结论：无多余文件或代码。

---

## 5. 完毕性审计

### 5.1 Phase C Gate 量化目标完成度

| Gate | 阈值 | 实测 | 完成 |
| --- | --- | --- | --- |
| C-1 | 7/7 | 7/7 | ✅ |
| C-2 | 200/200 | 200/200 | ✅ |
| C-3 | 100% | 200/200 | ✅ |
| C-4 | 50/50 | 50/50 | ✅ |
| C-5 | 50/50 | 50/50 | ✅ |

### 5.2 工程闭环完成度

| 检查项 | 完成 |
| --- | --- |
| gate 有可执行脚本入口 | ✅ `scripts/run_phase_c_gate.py` + `uv run mind-phase-c-gate` |
| gate 有 pytest 覆盖 | ✅ `test_phase_c_gate.py` |
| Phase B gate 无回归 | ✅ |
| ruff / mypy 全部通过 | ✅ |
| 验收报告已落地 | ✅ |
| 文档索引已更新 | ✅ |

### 5.3 未完成项（非阻断）

无阻断 Phase C 通过的缺口。以下为后续阶段可推进的方向：

- `_enforce_budget` 仍在 Python 侧遍历全部 budget events，Phase D 前应收敛到 SQL 级过滤
- `_retrieve` 与 `raw_records_for_episode()` 仍存在全表扫描路径
- `_summarize_text` 仍是占位实现

---

## 6. 改进（已修复）

### 改进 GC-I-1：Phase C gate 预算拒绝判定应增加对象不变性校验

**严重程度**：低（defense-in-depth）

**现象**：

gate 对 `budget` 类调用只验证 `outcome == REJECTED + error_code == BUDGET_EXHAUSTED + budget_event_delta == 0`，但未验证 `before_objects == after_objects`。

对比之下，`rollback` 类调用同时验证了对象快照不变性。两者在设计意图上是对称的（均应无状态副作用），但检查强度不对称。

当前实现正确（预算检查在所有写入之前触发，对象不可能变化），但如果后续代码变更将预算检查位置后移，该遗漏将无法被 gate 检出。

对象快照已在每次调用前后取过，增加此检查零额外开销。

**修复**：

在 `budget_rejected` 判定中增加 `and before_objects == after_objects`。

---

## 7. 观察（非阻断）

### O-1：成功调用分布略不均衡

60 条成功调用的分布为 write_raw / read / retrieve / summarize / link 各 10 条，reflect / reorganize_simple 各 5 条。C-1 只要求 smoke 覆盖，C-2 只要求 200/200 schema 合规，不要求均匀分布。但后续 `PrimitiveGoldenCalls v2` 可考虑更均衡的分配。

### O-2：write_raw 无异常测试场景

40 条异常调用覆盖了 read / retrieve / summarize / link / reflect / reorganize_simple，但未覆盖 write_raw。write_raw 的失败路径较少（主要是预算和可由 Pydantic 拦截的 schema 错误），当前覆盖合理，但后续可补充 episode_id 引用检查等场景。

### O-3：`c1_pass` 硬编码 `== 7`

规范字面要求 `7/7`，硬编码忠实于规范。但若未来新增 primitive，此处不会自动更新。如使用 `len(PrimitiveName)` 可实现前向兼容，但改动必要性低。

### O-4：retrieve 成功调用未覆盖 `status_filter`

10 条 retrieve 成功调用的 filters 覆盖了 `object_types` 和 `episode_id`，但未覆盖 `status_filter` 或 `time_window` filter 组合。

### O-5：per-call service 创建可优化

200 次调用每次都会新建 `_FaultInjectingPrimitiveService`。rollback 调用需要独立实例（各自配置 `inject_fault_for`），但非 rollback 调用（150 次）理论上可复用同一实例。不影响正确性，仅为性能观察。

### O-6：gate 只通过标签区分场景

golden call 的四类场景（success / abnormal / budget / rollback）完全依赖 expectation tags 区分。如果 tag 标注错误（如 budget 调用漏标 `"budget"` tag），gate 不会将其计入 C-4 统计。当前标注由 `_build_*` 函数自动生成，无手工标注风险。

---

## 8. 运行时流程验证

以下为独立追踪 `PrimitiveRuntime.execute_write` 和 `execute_read` 的关键发现：

### 写入路径（execute_write）

```
1. schema 校验 → 失败则 FAILURE + call_log（外部记录）
2. with store.transaction():
   3. handler 执行（含 _enforce_budget + 写入 + _after_write_operation）
   4. handler 成功 → call_log + budget_events 写入事务 → 提交
   5. PrimitiveRejectedError → 事务回滚 → call_log 外部记录 → REJECTED
   6. 其他 Exception → 事务回滚 → call_log 外部记录 → ROLLED_BACK
```

关键结论：

- budget events 在事务内记录 → rollback 时一并撤销 → `budget_event_delta == 0` ✅
- call log 在 REJECTED / ROLLED_BACK 时于事务外记录 → `log_count_delta == 1` ✅
- `_after_write_operation` 在事务内、写后提交前触发 → 回滚覆盖所有已写入对象 ✅

### 读取路径（execute_read）

```
1. schema 校验
2. handler 执行（含 _enforce_budget）
3. 无事务包裹
```

budget 检查在 handler 内触发，read handler 无写入路径，拒绝后状态不变。✅

---

## 9. 修复后回归验证

| 验证项 | 结果 |
| --- | --- |
| pytest 22/22 | ✅ 通过 |
| ruff check | ✅ All checks passed |
| mypy | ✅ Success: no issues found in 23 source files |
| Phase B gate | ✅ phase_b_gate=PASS |
| Phase C gate | ✅ phase_c_gate=PASS（200/200、7/7、50/50、50/50） |

---

## 10. 各文件审计摘要

### 10.1 `mind/fixtures/primitive_golden_calls.py`（新增，469 行）

**职责**：Phase C 的 200 条固定 golden call 工件。

**审计结论**：✅ 合格

- 200 = 60 success + 40 abnormal + 50 budget + 50 rollback，`build_primitive_golden_calls_v1()` 硬编码校验 `len == 200`
- `build_phase_c_seed_objects()` 组合 showcase + 20 episodes + 2 状态测试对象（archived / invalid），覆盖异常路径所需的预置对象
- ID 常量（`SHOWCASE_RAW_ID` 等）与 `build_core_object_showcase()` 返回的对象 ID 一一对应，已交叉验证
- budget 调用使用 `budget_limit=0.0` + 唯一 `budget_scope_id`，保证隔离且必定触发拒绝
- rollback 调用正确排除了 read / retrieve（无写入路径），仅覆盖 5 个写入 primitive
- `_build_loop_cases` 为首条标记 `"smoke"` tag，7 个 primitive 各恰好 1 条 smoke

### 10.2 `mind/primitives/phase_c.py`（新增，323 行）

**职责**：Phase C gate 自动化评估与结果结构。

**审计结论**：✅ 合格

- `PhaseCGateResult` 的 `c1_pass` ~ `c5_pass` 与 [phase_gates.md](../foundation/phase_gates.md) 逐条吻合
- `evaluate_phase_c_gate` 为每次调用取对象快照、日志计数、budget event 计数，验证逻辑覆盖全部 5 个 gate
- `_FaultInjectingPrimitiveService` 通过方法覆盖注入故障，干净且不影响基类类型签名
- `_request_schema_valid` 和 `_response_schema_valid` 分别校验请求和响应的 Pydantic 模型
- `_log_has_required_fields` 做 round-trip model_validate + 字段存在性检查
- `assert_phase_c_gate` 为每个 gate 提供具体的失败计数信息

### 10.3 `mind/primitives/service.py`（修改，+6 行）

**职责**：为 5 个写入 primitive 添加 `_after_write_operation` hook。

**审计结论**：✅ 合格

- hook 在基类为 no-op，仅被 `_FaultInjectingPrimitiveService` 覆盖用于 C-5 fault injection
- 5 个写入 primitive（write_raw / summarize / link / reflect / reorganize_simple）均在写入完成后、handler 返回前调用 hook
- read / retrieve 无 hook 调用（正确——无写入副作用）
- `reorganize_simple` 的 hook 在 for 循环外调用，保证多目标写入的原子回滚

### 10.4 `scripts/run_phase_c_gate.py`（新增，21 行）

**审计结论**：✅ 合格。与 `run_phase_b_gate.py` 结构对称。

### 10.5 `tests/test_phase_c_gate.py`（新增，34 行）

**审计结论**：✅ 合格

- `test_primitive_golden_calls_v1_has_required_coverage`：验证 200 条 + tag 分布
- `test_phase_c_gate_metrics`：运行完整 gate 并逐项断言指标

### 10.6 `mind/cli.py`（修改，+34 行）

**审计结论**：✅ 合格。`phase_c_gate_main` 与 `phase_b_gate_main` 结构对称。

### 10.7 `pyproject.toml`（修改，+1 行）

**审计结论**：✅ 合格。新增 `mind-phase-c-gate = "mind.cli:phase_c_gate_main"` entry point。

### 10.8 `docs/reports/phase_c_acceptance_report.md`（新增，162 行）

**审计结论**：✅ 合格。验收数据与当前实测一致。

### 10.9 文档更新

| 文件 | 变更摘要 | 审计结论 |
| --- | --- | --- |
| `README.md` | primitive 列表更新为冻结 7 项；当前状态更新为 Phase C gate 通过；运行方式加入 Phase C gate | ✅ |
| `docs/README.md` | 索引加入 phase_c 审计和验收报告；查询入口更新 | ✅ |
| `design_breakdown.md` | primitive 列表更新为冻结 7 项 | ✅ |
| `phase_c_startup_checklist.md` | §2 / §3.2 / §4 / §7 / §8 / §10 / §11 全面更新为完成态 | ✅ |
| `implementation_stack.md` | Phase C 技术栈状态更新 | ✅ |
| `phase_c_independent_audit.md` | 加入时点说明，指向 acceptance report | ✅ |

---

## 11. 最终结论

PrimitiveGoldenCalls v1 和 Phase C smoke gate 的实现在合理性、必要性和完毕性三个维度均通过审计。

- **合理性**：架构设计清晰，fault injection 机制干净，gate 判定逻辑忠实于规范
- **必要性**：无多余文件或代码，每个文件都服务于明确的工程目标
- **完毕性**：C-1 ~ C-5 全部量化通过，工程闭环（脚本 / 测试 / 文档）完整

Phase C 可视为正式通过。后续应转向 Phase D：Retrieval / Workspace。
