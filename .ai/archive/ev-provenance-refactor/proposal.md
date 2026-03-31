# Change Proposal: Evidence Provenance Refactor — 删除 src、用 batch_id 溯源

## Metadata

- Change ID: `ev-provenance-refactor`
- Type: `refactor`
- Status: `approved`
- Spec impact: `update required`
- Verification profile: `feature`
- Owner: `agent`
- Related specs: `语义翻译层 (Doc/core/语义翻译层.md)`

## Summary

1. **从 `ev()` 语法中删除 `src` 参数**，不再让 LLM 输出 `src="turn_X"`。
2. **用 `batch_id`（事实簇 GUID）作为 evidence 的主溯源锚点**。
   每次上层调用 `Memory.add()` 产生一个 `batch_id`，所有该批次内的
   statement/evidence 天然归属同一个事实簇，不需要 LLM 重复输出来源标签。
3. **在 evidence 表增加 `batch_id` 列**，建立结构化外键关系，
   取代当前 `src` 文本字段的弱追踪。
4. **保留 `span` 和 `conf`**，它们由 LLM 产出且有独立价值。

## Why Now

- `src="turn_X"` 是弱文本标签，不是外键，不能全局定位来源。
- 每条 `ev()` 多输出 `src="turn_X"` 浪费 ~8–12 token，无实际业务收益。
- MIND 是对话分析系统而非在线对话 agent，上层传入的对话粒度不可控。
  真正稳定的来源边界是"一次上传/一次分析调用"，即 `batch_id`。
- 当前 `batch_id` 已经存在且贯穿 statement/ref 全局化链路，
  evidence 是唯一没有结构化绑定 batch 的环节。

## In Scope

1. `ev()` 语法：删除 `src` 参数，保留 `conf` 和 `span`。
2. STL prompt：移除对 `src` 的要求。
3. Parser：移除 `src` 解析逻辑。
4. Models：从 `ParsedEvidence` 移除 `src` 字段。
5. Store：
   - evidence 表增加 `batch_id` 列（nullable，兼容旧数据）。
   - `insert_evidence()` 接口增加 `batch_id` 参数。
   - `store_program()` 传递 `batch_id` 到 evidence 插入。
   - 移除 `src` 相关写入。
6. Fake LLM：移除 `src` 生成。
7. Tests：更新 parser/store/phase2/phase3/eval 相关测试。
8. Eval datasets：从 `expected_evidence` 中移除 `src` 字段。
9. 设计文档 `Doc/core/语义翻译层.md`：更新 ev 语法描述和溯源模型。

## Out Of Scope

- 不改 `conv_id`、`turns`、`extraction_batches` 已有表结构。
- 不新增数据库迁移工具（表新增列用 nullable + DDL 幂等处理）。
- 不修改 memory 投影层（`source_session_id` 等向量层来源字段保持原样）。
- 不引入外部迁移框架（Alembic 等）。

## Proposed Changes

### 1. ev() 语法变更

Before:
```
ev($id, conf=N, src="turn_X", span="…")
```

After:
```
ev($id, conf=N, span="…")
```

`src` 被彻底移除。溯源改为系统侧自动关联：
`evidence.batch_id → extraction_batches.id → conversations.id`。

### 2. evidence 表 schema 变更

```sql
-- 新增列
ALTER TABLE evidence ADD COLUMN batch_id TEXT REFERENCES extraction_batches(id);

-- 移除 src 列（新建表时直接不含 src）
-- 旧数据中的 src 列不做主动迁移，DDL 重建时自然消失
```

实际实现策略：修改 DDL 模板，新建表不含 `src`、含 `batch_id`。
已有数据库中 `src` 列不做破坏性删除，仅不再写入。

### 3. 溯源查询模型

之前（弱标签）：
```sql
SELECT * FROM evidence WHERE src = 'turn_1';  -- 不精确
```

之后（结构化外键）：
```sql
-- 查某次分析产生的所有 evidence
SELECT * FROM evidence WHERE batch_id = ?;

-- 查某次分析对应的会话
SELECT e.*, b.conv_id
FROM evidence e
JOIN extraction_batches b ON e.batch_id = b.id
WHERE b.conv_id = ?;
```

### 4. Token 节省

每条 `ev()` 节省 `src="turn_X"` 约 8–12 token。
典型 STL 输出含 3–8 条 ev，单次调用节省 ~24–96 token。

## Reality Check

| 风险 | 评估 |
|------|------|
| 删除 `src` 后丢失"轮次级"定位 | `span` 已能定位原文片段；轮次偏移可从 `batch → turns` 间接获得。实际业务中 turn_X 从未被程序使用过，只是展示标签。 |
| 旧数据兼容 | `batch_id` 列设为 nullable。旧数据保留 `src` 列不删除，只是不再写入。 |
| 测试覆盖面 | 大量测试硬编码了 `src="turn_1"`，需要批量更新。不涉及逻辑变更，只是移除字段。 |
| 文档同步 | 设计文档 `Doc/core/语义翻译层.md` 需要同步更新 ev 语法。 |

## Acceptance Signals

1. `ev()` 不再包含 `src` 参数，prompt 中不要求 LLM 输出 `src`。
2. `ParsedEvidence` 不含 `src` 字段。
3. `evidence` 表有 `batch_id` 列且在 `store_program()` 中正确写入。
4. 可通过 `batch_id` 查询某次分析的所有 evidence。
5. 所有现有测试通过（更新后）。
6. eval datasets 中 `expected_evidence` 不含 `src`。

## Verification Plan

- Profile: `feature`
- Checks:
  - 全量 pytest 通过
  - evidence 表 DDL 正确（包含 `batch_id`，不含 `src`）
  - `store_program()` 写入 evidence 时传入 `batch_id`
  - prompt 中无 `src` 要求
  - parser 不再解析 `src`
- 手动验证：review schema DDL 和 prompt 文本

## Open Questions

无。方案基于当前代码现状，所有修改路径已确认。

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
