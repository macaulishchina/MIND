# Phase C 启动清单

日期：`2026-03-08`

适用对象：

- 当前仓库的 Phase B 基线实现
- 即将开始的 Phase C `Primitive API` 工作

相关文档：

- 规范定义见 [spec.md](../foundation/spec.md)
- 阶段 gate 见 [phase_gates.md](../foundation/phase_gates.md)
- 技术栈冻结见 [implementation_stack.md](../foundation/implementation_stack.md)
- Phase B 验收见 [phase_b_acceptance_report.md](../reports/phase_b_acceptance_report.md)
- Phase B 独立审计见 [phase_b_independent_audit.md](../reports/phase_b_independent_audit.md)

---

## 1. 目的

这份清单不重复定义 Phase C 的目标，而是把“进入 Phase C 前需要确认什么、按什么顺序做、先解决哪些问题”收束成一个可执行启动面。

Phase C 的核心任务不是基础设施迁移，而是：

- 让 `7` 个 primitives 成为稳定接口
- 冻结 request / response contract
- 建立结构化日志、预算约束、失败原子性和 contract tests

对应 gate 见 [phase_gates.md](../foundation/phase_gates.md#L467)。

---

## 2. 当前起点

当前仓库已经满足 Phase C 启动的最低前置条件：

- Phase A 规范已冻结
- Phase B gate 已通过
- 独立审计已完成，且没有留下阻断 Phase C 启动的未修复缺陷

当前已验证事实：

- `python3 -m unittest discover -s tests -v`：`8/8` 通过
- `python3 scripts/run_phase_b_gate.py`：`B-1 ~ B-5` 全部 `PASS`

当前已有的底座能力：

- 统一对象 schema validator
- append-only SQLite store
- source trace / cycle / version chain 审计
- episode replay 与事件顺序 hash
- `GoldenEpisodeSet v1`
- `MemoryStore` 最小协议
- 可复用的 Phase B gate 入口

---

## 3. 启动条件检查

### 3.1 已满足

- [x] `8/8` 核心对象类型与统一字段定义已冻结
- [x] `7/7` primitives 语义与 contract 模板已冻结
- [x] Phase B 内核已能 round-trip、replay、trace audit、version audit
- [x] `insert_objects()` 批量写入已具备原子性
- [x] 跨版本类型变更已被 store 拒绝
- [x] `MemoryStore` 协议已从 SQLite 实现中抽出

### 3.2 启动后第一时间要做

- [x] 建立 `pyproject.toml`
- [x] 建立 `uv` 依赖与命令入口
- [x] 引入 `pytest`
- [x] 引入 `ruff`
- [x] 引入 `mypy`
- [x] 建立 primitive request / response 的 typed schema

这些项不阻断 Phase C 启动，但应作为第一个工作流优先完成；否则后续 contract test 和接口迭代会立刻失去约束。

---

## 4. 优先级分级

### P0：Phase C 第一周内必须完成

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

### P1：Phase C 周期内应完成

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
   - 建立 `>= 200` 条 primitive 调用样例
   - 覆盖正常、异常、超预算、回滚场景

5. **对象覆盖补强**
   - 把 `EntityNode / LinkEdge / SchemaNote / WorkspaceView` 纳入端到端调用路径
   - 不再只靠 showcase 验证“可被 store 接受”

### P2：Phase C 中后段或 D 前完成

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

1. `MemoryStore` 还没有 primitive 级事务 API。
2. `B-5` 当前更接近“metadata 字段存在率”，还不是严格 typed compliance。
3. `WorkspaceView` 的关键 contract 已在 spec 冻结，但 validator 尚未执行这些约束。

### 中优先级问题

1. `LinkEdge` 的语义引用不在 integrity report 审计范围内。
2. `GoldenEpisodeSet v1` 的 episode 级路径只覆盖 `4/8` 对象类型。
3. `raw_records_for_episode()` 仍然是全表扫描。

### 低优先级问题

1. 时间戳一致性规则尚未执行化。
2. `content` 深度校验尚未冻结。
3. 文档索引仍可继续补全，例如将独立审计纳入统一入口。

---

## 8. 开放问题

以下问题建议在 Phase C 第一周内明确，不要边做边摇摆：

1. primitive 的默认暴露形态是否统一为 Python service object，而不是裸函数集合？
2. `MemoryStore` 的事务 API 采用显式 `transaction()` 上下文，还是更高层的 unit-of-work？
3. `budget state` 是否在 Phase C 就落为可持久化对象，还是先作为独立 side-channel contract？
4. `reorganize_simple` 是否在实现层立即拆成内部子操作，还是先保留单入口、内部枚举 action kind？
5. `Pydantic v2` 是否只用于 request / response，还是直接逐步替换当前对象 validator？

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

当且仅当以下条件满足时，可以认为 Phase C 启动完成并进入稳定开发轨道：

- 工程骨架已经统一
- `7` 个 primitive 的 typed contract 已冻结
- primitive 的执行边界和失败语义已明确
- 结构化日志模型已存在
- transaction / rollback 路径已可测试
- `PrimitiveGoldenCalls v1` 已开始建立

这并不等于 `Phase C PASS`，但意味着可以开始按 gate 收敛，而不是继续争论起步方式。

---

## 11. 一句话结论

Phase C 现在可以启动，但应该按“先 contract、再事务、再日志、再覆盖面”的顺序推进，而不是先引入新基础设施或提前做检索系统。
