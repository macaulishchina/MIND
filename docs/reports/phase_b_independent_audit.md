# Phase B 独立审计报告

审计日期：`2026-03-09`

审计人：独立审计（非原开发者）

审计对象：

- Phase B 全部内核代码：[schema.py](../../mind/kernel/schema.py)、[store.py](../../mind/kernel/store.py)、[integrity.py](../../mind/kernel/integrity.py)、[replay.py](../../mind/kernel/replay.py)、[phase_b.py](../../mind/kernel/phase_b.py)
- 固定数据集：[golden_episode_set.py](../../mind/fixtures/golden_episode_set.py)
- 测试套件：[test_phase_b_gate.py](../../tests/test_phase_b_gate.py)
- Gate 脚本：[run_phase_b_gate.py](../../scripts/run_phase_b_gate.py)
- 原始验收报告：[phase_b_acceptance_report.md](./phase_b_acceptance_report.md)

---

## 0. 总结论

**Phase B 独立审计结论：`PASS`**

B-1 至 B-5 五项 MUST-PASS 指标经独立复现全部通过，原始报告的数据声明准确。

独立审计发现 **2 项缺陷**和 **8 项观察**。2 项缺陷已在审计后立即修复并通过回归测试验证（8/8 测试通过，gate PASS）。

---

## 1. 审计方法

本次审计不依赖原开发者的任何解释或注释，完全从以下独立操作出发：

1. **代码通读**：逐文件阅读 `mind/kernel/` 五个模块，建立独立理解
2. **测试复现**：运行 `python3 -m unittest discover -s tests -v`，确认 `6/6` 通过
3. **Gate 复现**：运行 `python3 scripts/run_phase_b_gate.py`，确认 B-1 至 B-5 全部 PASS
4. **独立探测**：编写 18 个独立探测脚本（12 + 6），覆盖原测试未触及的边界条件、原子性、跨版本不变量、schema 验证深度

---

## 2. Gate 指标复现

| Gate | 原报告声明 | 独立复现结果 | 一致性 |
| --- | --- | --- | --- |
| B-1 | 142/142 round-trip | 142/142 | ✅ 一致 |
| B-2 | SourceTraceCoverage = 1.00 | 1.00 | ✅ 一致 |
| B-3 | dangling 0 / cycle 0 / version issues 0 | 0 / 0 / 0 | ✅ 一致 |
| B-4 | 20/20 replay | 20/20 | ✅ 一致 |
| B-5 | metadata coverage = 1.00 | 1.00 | ✅ 一致 |

**复现测试通过数：6/6（2.205s）**

结论：原报告所有量化声明经独立验证为准确。

---

## 3. 发现的缺陷

### 缺陷 I-1：`insert_objects()` 不具备原子性 — ✅ 已修复

**严重程度**：中（Phase C 阻断 — C-5 明确要求失败原子性）

**现象**：

`SQLiteMemoryStore` 的 `insert_object()` 每次调用内部独立 `commit()`。当使用循环批量插入时（如在 gate 测试的 fixture load 中），如果第 N 个对象写入失败，前 N-1 个对象已不可撤回地持久化。

**复现**：

```python
store = SQLiteMemoryStore(":memory:")
objects = [valid_obj_1, valid_obj_2, valid_obj_3, invalid_obj_4]
for obj in objects:
    try:
        store.insert_object(obj)
    except Exception:
        pass
# 结果：3 个对象已持久化，第 4 个失败。无法回滚前 3 个。
```

**影响范围**：

- Phase B gate 不测试批量写入失败场景，因此不影响 B-1~B-5 判定
- Phase C gate C-5 (`失败原子性: 50/50 注入失败场景无 partial write`) 会直接暴露此问题
- 如果不修复，Phase C 的 primitive contract 无法保证写入操作的 all-or-nothing 语义

**修复**：

- `insert_object()` 不再自行 `commit()`，改为由调用方控制事务边界
- `insert_objects()` 重写为：先批量 `ensure_valid_object()`，再在同一事务内执行全部 INSERT，失败时 `rollback()`
- 回归测试 `test_insert_objects_is_atomic` 已添加并通过

---

### 缺陷 I-2：Store 允许跨版本类型变更 — ✅ 已修复

**严重程度**：中

**现象**：

`store.py` 在写入新版本时检查版本连续性和 dangling refs，但不检查对象类型是否与前一版本一致。一个对象可以从 `SummaryNote` v1 变为 `ReflectionNote` v2。

**复现**：

```python
store = SQLiteMemoryStore(":memory:")
store.insert_object(summary_note_v1)  # type = SummaryNote, id = X
store.insert_object(reflection_note_v2)  # type = ReflectionNote, id = X, version = 2
# 写入成功，无报错
```

**Spec 依据**：

[spec.md §7.4](../foundation/spec.md) 明确要求：

> 新版本必须继承对象身份并更新 `version`

"继承对象身份"合理地要求类型一致，因为 `type` 是对象身份的核心组成部分。

**影响范围**：

- Phase B gate 未直接测试跨版本类型变更，因此不影响 B-1~B-5 判定
- 如果 Phase C 的 primitive（如 `summarize` 或 `reflect`）意外产生类型变更的版本，将违反 spec 的身份不变量且无任何防护
- integrity.py 的审计也不检查此不变量

**修复**：

- `_validate_and_insert()` 在写入 version > 1 时，读取前一版本并校验 `type` 字段一致性，不一致时抛出 `StoreError`
- 回归测试 `test_store_rejects_type_change_across_versions` 已添加并通过

---

## 4. 观察项

以下观察不影响 Phase B gate 判定，但会影响后续阶段的质量和安全性。

### O-1：Golden episodes 类型覆盖不均衡

**发现**：GoldenEpisodeSet v1 的 20 个 episodes、142 个对象仅使用 4/8 种对象类型：

- 使用中：`RawRecord`、`TaskEpisode`、`SummaryNote`、`ReflectionNote`
- 仅在 showcase 中出现：`EntityNode`、`LinkEdge`、`SchemaNote`、`WorkspaceView`

Showcase 验证了 8/8 类型可被 store 接受，但未参与 episode 级别的端到端 round-trip 和 replay 测试。

**影响**：Phase C 开始使用 `link` 和 `reorganize_simple` primitive 时，`EntityNode` 和 `LinkEdge` 的端到端路径未经 episode 级别验证。

**建议**：Phase C 扩展 `GoldenEpisodeSet` 或新增 `PrimitiveGoldenCalls v1` 时补充覆盖。

---

### O-2：integrity.py 不审计 `LinkEdge.content.src_id/dst_id` 存在性

**发现**：`build_integrity_report()` 只检查 `source_refs` 的 dangling refs，不检查 `LinkEdge.content` 中的 `src_id` 和 `dst_id` 是否指向存在的对象。

**复现**：插入一个 `LinkEdge`，其 `content.src_id` 指向不存在的对象 → integrity report 显示 `dangling_refs: 0`。

**影响**：Phase C 的 `link` primitive 会大量生成 `LinkEdge`，如果 content 中的引用不被审计，edge 的语义完整性将没有自动化防护。

**建议**：Phase C 补充 integrity 审计范围。

---

### O-3：`raw_records_for_episode()` 全表扫描

**发现**：`store.py` 中 `raw_records_for_episode()` 通过 `iter_objects()` 遍历全表后在 Python 侧过滤 `episode_id`。

**影响**：Phase B 数据量极小（142 对象），性能无影响。Phase C/D 数据增长后需要 SQL 级 `WHERE` 过滤 + `episode_id` 索引。

**建议**：Phase C 存储抽象层（MemoryStore Protocol）的实现中补充。原验收报告 §5 已提及此风险。

---

### O-4：schema.py 不强制 `slot_limit` 约束

**发现**：`WorkspaceView` 的 `_validate_slot()` 验证了每个 slot 的结构，但不验证 `len(slots) <= slot_limit`。

**复现**：`WorkspaceView` 设置 `slot_limit=2` 但包含 3 个 slot → `validate_object()` 返回空错误列表。

**Spec 依据**：[spec.md §4.5](../foundation/spec.md) 明确规定 `slot_count <= K`。

**影响**：Phase D gate 将正式验收 workspace discipline。但如果 Phase C 的 `reorganize_simple` primitive 构造 WorkspaceView 时超出 slot_limit，将无自动防护。

**建议**：在 schema.py 中补充 `slot_limit` 校验，或至少在 Phase D 前完成。

---

### O-5：schema.py 不验证时间一致性

**发现**：

- `created_at > updated_at` 的对象被接受（逻辑上不合理）
- `version=1` 的对象 `created_at ≠ updated_at` 也被接受（v1 对象尚未被修订，两个时间戳应相等）

**影响**：当前 golden episodes 的时间戳全部一致，因此不影响 B-1~B-5。但如果 Phase C primitive 生成时间戳不一致的对象，将无防护。

**建议**：Phase C 扩展 schema 验证时补充。

---

### O-6：schema.py 不验证 metadata 字段值类型

**发现**：schema 验证器仅检查 metadata 必填字段是否存在，不检查其值类型。例如：

- `EntityNode.metadata.alias` 接受字符串（应为列表）
- `SchemaNote.metadata.stability_score` 接受字符串 `"not-a-number"`（应为数值）

**影响**：Phase B 的 metadata 覆盖率指标（B-5）只要求"必填字段存在"，类型检查不在 gate 要求范围内。但 Phase C primitive 输出的 metadata 如果类型错误，将无自动防护。

**建议**：Phase C 考虑引入 Pydantic model 或在 validate_object 中增加值类型校验。

---

### O-7：`id` 非空校验已实现，`content` 未校验

**发现**：`validate_object()` 正确拒绝空字符串 `id`，但接受空字符串 `content`。

**影响**：`content` 类型因对象类型而异（字符串、dict 等），Phase B 不对 content 做深度校验是合理的。但空 content 在语义上通常无意义。

**建议**：低优先级。Phase C 可在 primitive 层面防护。

---

### O-8：`priority` 边界校验已正确实现

**发现（正面）**：`priority=1.01` 和 `priority=-0.01` 均被正确拒绝，`[0, 1]` 边界校验工作正常。

---

## 5. 对原验收报告的评审

### 准确性

原报告所有量化数据经独立验证为准确，未发现数据篡改或误报。

### 覆盖范围

原报告 §5（非阻断风险）已正确识别了以下风险：
- SQLite 单文件不适合并发写入 → 与本报告 O-3 相关
- replay 依赖 `timestamp_order` → 准确
- `LinkEdge.content.src_id/dst_id` 不在 integrity 审计范围 → 与本报告 O-2 一致
- `WorkspaceView` slot discipline 延迟到 Phase D → 与本报告 O-4 一致

原报告 **未识别** 的问题：
1. 写入原子性缺陷（缺陷 I-1）— 这是一个实际的 bug，不仅是风险
2. 跨版本类型变更（缺陷 I-2）— 这是一个 spec 不变量违反
3. 时间戳一致性（O-5）、metadata 值类型深度（O-6）— 这些是验证深度不足

### 评审结论

原报告对 B-1~B-5 的判定是正确的。报告质量较高，§5 的风险识别覆盖了主要方向。但作为自我审查，未能发现两项实际缺陷（I-1, I-2），这在预期之内。

---

## 6. Phase C 启动前必须完成的修复

| 编号 | 修复项 | 原因 | 状态 |
| --- | --- | --- | --- |
| I-1 | `insert_object()` 的批量写入提供事务包装 | Phase C gate C-5 要求失败原子性 | ✅ 已修复 |
| I-2 | `insert_object()` 校验跨版本类型一致性 | spec §7.4 身份继承要求 | ✅ 已修复 |

---

## 7. Phase C 启动建议

以下观察项不阻断 Phase B，但建议在 Phase C 开发周期内逐步解决：

| 优先级 | 观察项 | 建议时机 |
| --- | --- | --- |
| 高 | O-2：LinkEdge content 引用审计 | Phase C `link` primitive 实现时 |
| 高 | O-6：metadata 值类型校验 | Phase C contract tests 设计时 |
| 中 | O-4：slot_limit 校验 | Phase C `reorganize_simple` 实现时 |
| 中 | O-5：时间戳一致性校验 | Phase C schema 增强时 |
| 中 | O-1：golden episodes 类型覆盖 | PrimitiveGoldenCalls v1 设计时 |
| 低 | O-3：raw_records_for_episode SQL 优化 | Phase C 存储抽象层实现时 |
| 低 | O-7：content 非空校验 | 按需 |

---

## 8. 最终结论

**Phase B 独立审计结论：`PASS`**

- 五项 MUST-PASS 指标全部通过，数据准确
- 内核四个底座能力（append-only、source trace、version chain、replay fidelity）已具备
- 发现 2 项缺陷，均已修复并通过回归测试验证（8/8 测试通过，Phase B gate PASS）
- 发现 8 项观察，建议在 Phase C 周期内逐步处理
- 原验收报告质量合格，自我审查之外的盲点已由本次独立审计覆盖

**Phase C 启动条件已满足。**
