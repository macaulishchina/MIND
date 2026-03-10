# Phase H 验收报告

验收日期：`2026-03-10`

验收对象版本：

- `git HEAD = cf3c698`
- 本报告对应对象为 `cf3c698` 之后、尚未提交的本地工作树（包含本轮 Phase H provenance / governance / conceal / gate 改动）

数据 / fixture 版本：

- `GoldenEpisodeSet v1`
- `PrimitiveGoldenCalls v1`
- `Phase H` 最小 provenance / conceal regression fixture

验收对象：

- [phase_gates.md](../foundation/phase_gates.md)
- [phase_h_startup_checklist.md](../design/phase_h_startup_checklist.md)
- [provenance.py](../../mind/kernel/provenance.py)
- [governance.py](../../mind/kernel/governance.py)
- [store.py](../../mind/kernel/store.py)
- [postgres_store.py](../../mind/kernel/postgres_store.py)
- [service.py](../../mind/primitives/service.py)
- [phase_h.py](../../mind/governance/phase_h.py)
- [service.py](../../mind/governance/service.py)
- [run_phase_h_gate.py](../../scripts/run_phase_h_gate.py)
- [test_phase_h_gate.py](../../tests/test_phase_h_gate.py)
- [test_governance_service.py](../../tests/test_governance_service.py)
- [test_concealment_online.py](../../tests/test_concealment_online.py)
- [test_concealment_offline.py](../../tests/test_concealment_offline.py)

相关文档：

- Phase H 启动与收敛轨迹见 [../design/phase_h_startup_checklist.md](../design/phase_h_startup_checklist.md)
- Phase H gate 与阶段定义见 [../foundation/phase_gates.md](../foundation/phase_gates.md)

验收范围：

- `H-1` direct provenance 绑定完整率
- `H-2` authoritative provenance 完整性
- `H-3` 低权限 provenance 读取隔离
- `H-4` 高权限 provenance 摘要收敛
- `H-5` `conceal` 在线隔离有效性
- `H-6` `conceal` 离线隔离有效性
- `H-7` 治理审计链完整率
- `H-8` provenance 优化泄露防护

验收方法：

- 按 [phase_gates.md](../foundation/phase_gates.md) 的 `H-1 ~ H-8` 逐条核对
- 运行 `python3 -m pytest -q`
- 运行 `.venv/bin/ruff check mind tests scripts`
- 运行 `.venv/bin/mypy`
- 运行 `python3 scripts/run_phase_b_gate.py`
- 运行 `python3 scripts/run_phase_c_gate.py`
- 运行 `python3 scripts/run_phase_e_gate.py`
- 运行 `python3 scripts/run_phase_h_gate.py`
- 运行 `python3 scripts/run_phase_g_gate.py`

## 1. 结论

Phase H 本次验收结论：`PASS`

判定依据：

- `H-1 ~ H-8` 八项 MUST-PASS 指标全部通过
- direct provenance、capability 边界、`plan / preview / execute(conceal)`、online / offline conceal 隔离与 formal gate 已形成统一闭环
- 本地全量静态检查和单元测试通过，未发现对已完成 Phase B/C/E/G 的回归

## 2. Gate 结果

| Gate | 阈值 | 结果 | 结论 |
| --- | --- | --- | --- |
| `H-1` | `RawRecord / ImportedRawRecord` authoritative direct provenance 绑定率 `= 100%` | `3 / 3` | `PASS` |
| `H-2` | duplicate `= 0`，orphan `= 0`，bound type 校验 `= 100%` | `0 / 0 / 3` | `PASS` |
| `H-3` | 低权限 provenance 读取成功率 `= 0` | `2 / 2` 次阻断，普通 read 无 provenance 摘要 | `PASS` |
| `H-4` | 高权限摘要返回率 `= 100%`，超范围高敏字段泄露率 `= 0` | `2 / 2`，泄露 `0` | `PASS` |
| `H-5` | 被 conceal 对象在普通 online read / retrieve / workspace 默认不可见 | `3 / 3` | `PASS` |
| `H-6` | 被 conceal 对象在默认 offline replay / maintenance / ranking 默认不消费 | `3 / 3` | `PASS` |
| `H-7` | `plan / preview / execute` 审计链覆盖率 `= 100%` | `plan, preview, execute` | `PASS` |
| `H-8` | provenance 不参与 retrieval / ranking / weighting | query hit `0`，search / embedding basis 无漂移 | `PASS` |

补充验证：

| 验证项 | 结果 |
| --- | --- |
| `pytest -q` | `144 passed, 11 skipped` |
| `ruff check mind tests scripts` | `All checks passed!` |
| `mypy` | `Success: no issues found in 97 source files` |
| `python3 scripts/run_phase_b_gate.py` | `phase_b_gate=PASS` |
| `python3 scripts/run_phase_c_gate.py` | `phase_c_gate=PASS` |
| `python3 scripts/run_phase_e_gate.py` | `phase_e_gate=PASS` |
| `python3 scripts/run_phase_h_gate.py` | `phase_h_gate=PASS` |
| `python3 scripts/run_phase_g_gate.py` | `phase_g_gate=PASS` |

备注：

- 当前环境未设置 `MIND_TEST_POSTGRES_DSN`，因此 PostgreSQL 的新增 Phase H 集成回归用例仍处于跳过状态；本次验收未实际执行真实 PG 集成链路

## 3. 逐条核对

### `H-1` direct provenance 绑定完整率

核对结果：

- [service.py](../../mind/primitives/service.py) 的 `write_raw` 已为每条 `RawRecord` 绑定 authoritative direct provenance
- [phase_h.py](../../mind/governance/phase_h.py) gate 场景下共写入 `3` 条 `RawRecord`
- 当前 `authoritative_binding_count = 3 / 3`

判定：

- `H-1 = PASS`

### `H-2` authoritative provenance 完整性

核对结果：

- [store.py](../../mind/kernel/store.py) 与 [postgres_store.py](../../mind/kernel/postgres_store.py) 已提供 `provenance_ledger` 的持久化与读取
- 当前 gate 场景下：
  - duplicate provenance rows `= 0`
  - orphan provenance rows `= 0`
  - valid bound type count `= 3`

判定：

- `H-2 = PASS`

### `H-3` 低权限 provenance 读取隔离

核对结果：

- [contracts.py](../../mind/primitives/contracts.py) 已冻结 `memory_read` 与 `memory_read_with_provenance`
- [service.py](../../mind/primitives/service.py) 在低权限下会明确返回 `capability_required`
- gate 中两条低权限 provenance 读取尝试全部被阻断，普通 `read` 返回对象但不附带 provenance 摘要

判定：

- `H-3 = PASS`

### `H-4` 高权限 provenance 摘要收敛

核对结果：

- [service.py](../../mind/primitives/service.py) 的 `read_with_provenance` 会返回 runtime-safe `ProvenanceSummary`
- [service.py](../../mind/governance/service.py) 的 `preview_conceal` 也只返回冻结摘要
- 当前 gate 中：
  - 高权限 `read_with_provenance` 成功返回摘要
  - governance preview 成功返回摘要
  - `ip_addr / device_id / machine_fingerprint / session_id / request_id / conversation_id` 未泄露

判定：

- `H-4 = PASS`

### `H-5` `conceal` 在线隔离有效性

核对结果：

- [service.py](../../mind/primitives/service.py) 的普通 `read` 与 `retrieve` 默认隔离 concealed 对象
- [builder.py](../../mind/workspace/builder.py) 默认跳过 concealed candidate
- 当前 gate 中 concealed 对象在 `read / retrieve / workspace` 三条 online 路径上均默认不可见

判定：

- `H-5 = PASS`

### `H-6` `conceal` 离线隔离有效性

核对结果：

- [store.py](../../mind/kernel/store.py) 与 [postgres_store.py](../../mind/kernel/postgres_store.py) 的 `raw_records_for_episode` 默认过滤 concealed raw
- [replay.py](../../mind/offline/replay.py) 的 `select_replay_targets` 默认跳过 concealed 对象
- [service.py](../../mind/offline/service.py) 的默认 `reflect_episode` 路径因此不会消费 concealed raw

判定：

- `H-6 = PASS`

### `H-7` 治理审计链完整率

核对结果：

- [governance.py](../../mind/kernel/governance.py) 已冻结 `GovernanceAuditRecord`
- [service.py](../../mind/governance/service.py) 当前最小治理流程为 `plan -> preview -> execute(conceal)`
- 当前 gate 中审计链顺序稳定为 `plan, preview, execute`

判定：

- `H-7 = PASS`

### `H-8` provenance 优化泄露防护

核对结果：

- [retrieval.py](../../mind/kernel/retrieval.py) 的 `build_search_text` / `build_embedding_text` 会剥离 control-plane metadata
- gate 回归比较中，注入 `provenance / governance` metadata 后：
  - search text 不变
  - embedding text 不变
  - object embedding 不变
  - 基于 provenance-only token 的 query hit count `= 0`

判定：

- `H-8 = PASS`

## 4. 阻断项与剩余风险

阻断项：

- 未发现阻断 Phase H 通过的硬性问题

主要发现：

- Phase H 已把 provenance control plane、最小治理控制面与 conceal 隔离做成了正式 gate 能力
- provenance 与 `source_refs` 的职责边界现在在存储、读取、治理和检索四层都已经有可运行约束

非阻断风险：

- `ImportedRawRecord` 仍只有规范层口径，当前 gate 场景只覆盖 `RawRecord`
- PostgreSQL 的 Phase H 集成回归已补测试，但当前环境没有 DSN，尚未实际执行
- `erase(scope=full)`、mixed-source rewrite、artifact cleanup 仍然属于后续阶段，不在本次验收范围内

## 5. 最终结论

本次验收判定：

`Phase H = PASS`

当前状态：

- Phase H provenance foundation 已具备本地 formal gate
- 当前 gate 工件默认输出为 [artifacts/phase_h/gate_report.json](../../artifacts/phase_h/gate_report.json)
- 下一阶段可进入 `Phase I: Runtime Access Modes`
