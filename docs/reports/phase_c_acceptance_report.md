# Phase C 验收报告

验收日期：`2026-03-09`

验收对象：

- [spec.md](../foundation/spec.md)
- [phase_gates.md](../foundation/phase_gates.md)
- [primitive_golden_calls.py](../../mind/fixtures/primitive_golden_calls.py)
- [phase_c.py](../../mind/primitives/phase_c.py)
- [run_phase_c_gate.py](../../scripts/run_phase_c_gate.py)
- [test_phase_c_gate.py](../../tests/test_phase_c_gate.py)

相关文档：

- Phase C 启动与收敛清单见 [phase_c_startup_checklist.md](../design/phase_c_startup_checklist.md)
- Phase C 独立审计见 [phase_c_independent_audit.md](./phase_c_independent_audit.md)

验收范围：

- `C-1` Primitive 实现覆盖
- `C-2` 请求 / 响应 schema 合规率
- `C-3` 结构化日志覆盖率
- `C-4` 预算约束执行率
- `C-5` 失败原子性

验收方法：

- 按 [phase_gates.md](../foundation/phase_gates.md) 的 `C-1 ~ C-5` 逐条核对
- 运行 `python3 -m pytest -q`
- 运行 `.venv/bin/ruff check mind tests scripts`
- 运行 `.venv/bin/mypy`
- 运行 `python3 scripts/run_phase_b_gate.py`
- 运行 `python3 scripts/run_phase_c_gate.py`
- 审阅 [service.py](../../mind/primitives/service.py)、[runtime.py](../../mind/primitives/runtime.py)、[contracts.py](../../mind/primitives/contracts.py) 与 [store.py](../../mind/kernel/store.py)

## 1. 结论

Phase C 本次验收结论：`PASS`

判定依据：

- `C-1 ~ C-5` 五项 MUST-PASS 指标全部通过
- `PrimitiveGoldenCalls v1` 已建立并成为 Phase C gate 的固定工件
- 结构化日志、预算拒绝、失败回滚已经进入 gate，而不再只是零散单测
- Phase B gate 回归通过，未发现对底层存储与回放基线的回归

## 2. Gate 结果

| Gate | 阈值 | 结果 | 结论 |
| --- | --- | --- | --- |
| `C-1` | `7/7` primitives 可调用 | `7/7` | `PASS` |
| `C-2` | `PrimitiveGoldenCalls v1` 上 schema 合规 `200/200` | `200/200` | `PASS` |
| `C-3` | 结构化日志覆盖率 `100%` | `200/200` | `PASS` |
| `C-4` | 预算约束执行率 `50/50` | `50/50` | `PASS` |
| `C-5` | 失败原子性 `50/50` | `50/50` | `PASS` |

补充验证：

| 验证项 | 结果 |
| --- | --- |
| `pytest -q` | `22 passed in 5.30s` |
| `ruff check mind tests scripts` | `All checks passed!` |
| `mypy` | `Success: no issues found in 23 source files` |
| Phase B gate | `phase_b_gate=PASS` |
| Phase C gate | `phase_c_gate=PASS` |

## 3. 逐条核对

### `C-1` Primitive 实现覆盖

核对结果：

- [service.py](../../mind/primitives/service.py) 已提供 `write_raw / read / retrieve / summarize / link / reflect / reorganize_simple` 七个统一入口
- [test_phase_c_gate.py](../../tests/test_phase_c_gate.py) 对 `7/7` primitives 的 smoke 路径执行调用验证
- [phase_c.py](../../mind/primitives/phase_c.py) 将 `smoke_coverage=7/7` 收敛为 gate 输出

判定：

- `C-1 = PASS`

### `C-2` 请求 / 响应 schema 合规率

核对结果：

- [primitive_golden_calls.py](../../mind/fixtures/primitive_golden_calls.py) 固定 `200` 条 primitive 调用样例
- 样例覆盖正常、异常、超预算和回滚四类场景
- [phase_c.py](../../mind/primitives/phase_c.py) 对全部 `200/200` 样例执行 typed request / response 校验

判定：

- `C-2 = PASS`

### `C-3` 结构化日志覆盖率

核对结果：

- [runtime.py](../../mind/primitives/runtime.py) 为每次 primitive 调用统一生成 `PrimitiveCallLog`
- 日志字段覆盖 `actor / timestamp / target_ids / cost / outcome`
- 本次 gate 结果为 `structured_log_calls=200/200`

判定：

- `C-3 = PASS`

### `C-4` 预算约束执行率

核对结果：

- [service.py](../../mind/primitives/service.py) 在写入和读取路径统一执行预算约束
- `PrimitiveGoldenCalls v1` 中包含 `50` 条超预算拒绝场景
- 本次 gate 结果为 `budget_rejections=50/50`

判定：

- `C-4 = PASS`

### `C-5` 失败原子性

核对结果：

- [store.py](../../mind/kernel/store.py) 提供 primitive 级事务边界
- [service.py](../../mind/primitives/service.py) 提供 fault hook，用于注入失败并验证事务回滚
- `PrimitiveGoldenCalls v1` 中包含 `50` 条回滚场景，本次 gate 结果为 `rollback_atomic=50/50`

判定：

- `C-5 = PASS`

## 4. 阻断项与剩余风险

阻断项：

- 未发现阻断 Phase C 通过的硬性问题

主要发现：

- [phase_c_independent_audit.md](./phase_c_independent_audit.md) 中关于 `PrimitiveGoldenCalls v1` 的观察项已经关闭
- Phase C gate 已从“机制就位”推进到“量化阈值通过”，不再停留在 smoke + 少量样例阶段
- Phase C 现在具备稳定的 library-first primitive 层，可作为 Phase D Retrieval / Workspace 的调用底座

非阻断风险：

- `_enforce_budget` 仍按 `scope_id` 在 Python 侧过滤全部 budget events，Phase D 前应收敛为 SQL 级过滤
- `_retrieve` 和部分回放路径仍存在全表扫描，数据量增长后需要索引与 SQL 级约束
- `_summarize_text` 仍是占位摘要实现，质量优化属于后续阶段工作

## 5. 最终结论

本次验收判定：

`Phase C = PASS`

可进入下一阶段：

- 阶段 D：Retrieval / Workspace

建议阶段 D 的直接起步项：

- 将检索路径从全表扫描收敛为 SQL 级过滤与索引
- 在 PostgreSQL 后端上重放 Phase B / C 核心 gate
- 将 workspace builder 的 slot discipline、trace support 和 benchmark 工件正式纳入 gate
