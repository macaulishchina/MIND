# Phase C 启动清单

日期：`2026-03-08`
最近更新：`2026-03-09`

适用对象：

- 当前仓库的 Phase C 启动与收敛工作
- 已完成 Phase B、已通过本地 Phase C gate 的实现基线

相关文档：

- 规范定义见 [spec.md](../foundation/spec.md)
- 阶段 gate 见 [phase_gates.md](../foundation/phase_gates.md)
- 技术栈冻结见 [implementation_stack.md](../foundation/implementation_stack.md)
- Phase B 验收见 [phase_b_acceptance_report.md](../reports/phase_b_acceptance_report.md)
- Phase B 独立审计见 [phase_b_independent_audit.md](../reports/phase_b_independent_audit.md)
- Phase C 独立审计见 [phase_c_independent_audit.md](../reports/phase_c_independent_audit.md)
- Phase C 验收见 [phase_c_acceptance_report.md](../reports/phase_c_acceptance_report.md)

---

## 1. 目的

这份清单不重复定义 Phase C 的目标，而是把“进入 Phase C 前需要确认什么、按什么顺序做、先解决哪些问题”收束成一个可执行启动面。

Phase C 的核心任务不是基础设施迁移，而是：

- 让 `7` 个 primitives 成为稳定接口
- 冻结 request / response contract
- 建立结构化日志、预算约束、失败原子性和 contract tests

对应 gate 见 [phase_gates.md](../foundation/phase_gates.md#L467)。

---

## 2. 当前状态

当前仓库已经不再只是“满足 Phase C 启动条件”，而是已经完成启动项并通过本地 Phase C gate：

- Phase A 规范已冻结
- Phase B gate 已通过
- Phase C 独立审计已完成
- `PrimitiveGoldenCalls v1` 已建立
- Phase C gate 已通过

当前已验证事实：

- `python3 -m pytest -q`：`22 passed`
- `python3 scripts/run_phase_b_gate.py`：`B-1 ~ B-5` 全部 `PASS`
- `python3 scripts/run_phase_c_gate.py`：`C-1 ~ C-5` 全部 `PASS`

当前已有的底座能力：

- 统一对象 schema validator
- append-only SQLite store
- source trace / cycle / version chain 审计
- episode replay 与事件顺序 hash
- `GoldenEpisodeSet v1`
- `MemoryStore` 最小协议与 primitive 级事务边界
- typed primitive request / response contract
- `PrimitiveService`、结构化调用日志与 budget events
- `PrimitiveGoldenCalls v1`
- 可复用的 Phase B / Phase C gate 入口

---

## 3. 启动条件检查

### 3.1 已满足

- [x] `8/8` 核心对象类型与统一字段定义已冻结
- [x] `7/7` primitives 语义与 contract 模板已冻结
- [x] Phase B 内核已能 round-trip、replay、trace audit、version audit
- [x] `insert_objects()` 批量写入已具备原子性
- [x] 跨版本类型变更已被 store 拒绝
- [x] `MemoryStore` 协议已从 SQLite 实现中抽出

### 3.2 已完成的启动项

- [x] 建立 `pyproject.toml`
- [x] 建立 `uv` 依赖与命令入口
- [x] 引入 `pytest`
- [x] 引入 `ruff`
- [x] 引入 `mypy`
- [x] 建立 primitive request / response 的 typed schema

这些项已完成，保留在清单中作为 Phase C 启动收敛记录。

---

## 4. 优先级分级

### P0：已完成

1. **工程骨架收敛**
   - 建立 `pyproject.toml`
   - 统一 `uv` / `pytest` / `ruff` / `mypy`
   - 明确测试与脚本入口

2. **Primitive contract 模型化**
   - 为 `write_raw / read / retrieve / summarize / link / reflect / reorganize_simple` 建立 request / response schema
   - 错误码、预算失败、回滚失败必须显式建模

3. **Primitive 执行边界**
   - 确定 primitive 的库函数形态
   - 明确每个 primitive 是否写状态、写哪些对象、失败是否回滚
   - 不在这一阶段引入 FastAPI 路由

4. **事务边界设计**
   - 当前 `MemoryStore` 仅有对象级读写协议；Phase C 需要补充 primitive 级事务边界
   - 至少要能支撑“写对象 + 写日志 + 更新预算状态”的同事务提交

5. **结构化日志 contract**
   - 冻结 `actor / timestamp / target_ids / cost / outcome`
   - 明确 success / failure / rejected / rolled_back 等 outcome 值域

### P1：已完成

1. **metadata typed validation 增强**
   - 优先补 `EntityNode.alias`
   - 优先补 `SchemaNote.stability_score`
   - 优先补 `WorkspaceView.slot_limit`
   - 优先补 `LinkEdge.confidence`

2. **integrity 审计扩展**
   - 对 `LinkEdge.content.src_id / dst_id` 做存在性检查
   - 将跨版本类型一致性纳入离线 integrity report，而不只依赖写入时拒绝

3. **WorkspaceView validator 增强**
   - 补 `slot_count <= slot_limit`
   - 补 slot 的最小 traceability 规则

4. **PrimitiveGoldenCalls v1**
   - 已建立 `200` 条 primitive 调用样例
   - 已覆盖正常、异常、超预算、回滚场景

5. **对象覆盖补强**
   - 把 `EntityNode / LinkEdge / SchemaNote / WorkspaceView` 纳入端到端调用路径
   - 不再只靠 showcase 验证“可被 store 接受”

### P2：后续阶段继续推进

1. **局部性能债清理**
   - `raw_records_for_episode()` 改为 SQL 级过滤
   - 为后续 Postgres backend 保留接口形状

2. **时间一致性规则**
   - 补 `created_at <= updated_at`
   - 对 `version=1` 的默认时间规则给出明确约束

3. **低优先级内容深度校验**
   - 是否禁止空字符串 `content`
   - 是否进一步细化各对象 `content` 的 typed schema

---

## 5. 建议执行顺序

推荐顺序如下：

1. `工程骨架`
   - `pyproject.toml`
   - `uv`
   - `pytest`
   - `ruff`
   - `mypy`

2. `contract 层`
   - primitive request / response models
   - 统一错误模型
   - 统一日志模型

3. `运行时层`
   - primitive service objects / functions
   - transaction boundary
   - budget state interface

4. `验证层`
   - `PrimitiveGoldenCalls v1`
   - contract tests
   - rollback / fault injection tests

5. `补强层`
   - metadata typed validation
   - `LinkEdge` integrity
   - `WorkspaceView` contract 执行化

这个顺序的原则是：先冻结接口，再写实现；先保证失败语义和日志可审计，再追求功能覆盖。

---

## 6. 与 Phase C Gate 的映射

| Gate | 对应启动项 | 说明 |
| --- | --- | --- |
| `C-1` Primitive 实现覆盖 | `contract 层 + 运行时层` | `7/7` primitives 可调用 |
| `C-2` 请求 / 响应 schema 合规率 | `contract 层 + PrimitiveGoldenCalls v1` | 要求 typed schema 先稳定 |
| `C-3` 结构化日志覆盖率 | `日志模型 + 执行包装层` | 不能靠手工打印补 |
| `C-4` 预算约束执行率 | `budget state interface + error model` | 必须有显式拒绝语义 |
| `C-5` 失败原子性 | `transaction boundary + fault tests` | 这是当前最容易被低估的点 |

---

## 7. 当前已知问题与纠偏方向

### 高优先级问题

1. 当前无阻断 Phase C 的高优先级缺口。

### 中优先级问题

1. `_enforce_budget` 仍在 Python 侧遍历全部 budget events，Phase D 前应收敛到 SQL 级过滤。
2. `_retrieve` 与 `raw_records_for_episode()` 仍存在全表扫描路径。
3. 时间一致性规则（如 `created_at <= updated_at`）尚未执行化。

### 低优先级问题

1. `_summarize_text` 仍是占位实现，质量优化属于后续阶段工作。
2. `GoldenEpisodeSet v1` 仍主要服务 Phase B，episode 级对象覆盖仍可继续补强。
3. `content` 深度校验尚未冻结。

---

## 8. 关键决策收敛

以下关键决策已经在 Phase C 内收敛完成：

1. primitive 的默认暴露形态统一为 Python service object，而不是裸函数集合。
2. `MemoryStore` 的事务 API 采用显式 `transaction()` 上下文。
3. `budget state` 先以持久化 `budget_events` + contract 约束落地，不提前抽象为独立对象体系。
4. `reorganize_simple` 继续保留单入口，内部使用 action kind 区分子操作。
5. `Pydantic v2` 已用于 primitive request / response，对象 validator 继续按需增量补强。

---

## 9. Phase C 的明确非目标

以下内容不应在 Phase C 中抢跑：

- PostgreSQL 主存储迁移
- `pgvector` / `pg_trgm` 检索接入
- FastAPI 服务化部署
- Redis 缓存层
- 大对象存储
- Workspace builder 算法优化

这些都属于 Phase D 及以后。

---

## 10. 完成定义

以下条件现均已满足，因此可以认为 Phase C 启动工作已经完成并进入稳定开发轨道：

- 工程骨架已经统一
- `7` 个 primitive 的 typed contract 已冻结
- primitive 的执行边界和失败语义已明确
- 结构化日志模型已存在
- transaction / rollback 路径已可测试
- `PrimitiveGoldenCalls v1` 已建立并纳入 gate
- Phase C smoke gate 已通过

这不仅意味着“启动完成”，也意味着 Phase C 已经具备可验收、可回归的闭环。

---

## 11. 一句话结论

Phase C 启动工作已经完成；这份文档现在的作用是保留启动与收敛轨迹。后续重点应转向 Phase D 的 retrieval / workspace，而不是继续争论 Phase C 该如何起步。
