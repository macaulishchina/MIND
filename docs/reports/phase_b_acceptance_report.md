# Phase B 验收报告

验收日期：`2026-03-08`

验收对象：

- [spec.md](../foundation/spec.md)
- [phase_gates.md](../foundation/phase_gates.md)
- [run_phase_b_gate.py](../../scripts/run_phase_b_gate.py)
- [test_phase_b_gate.py](../../tests/test_phase_b_gate.py)

验收范围：

- `B-1` Ingest / Read round-trip 准确率
- `B-2` `SourceTraceCoverage`
- `B-3` 版本图完整性
- `B-4` Replay fidelity
- `B-5` 必填 metadata 覆盖率

验收方法：

- 按 [phase_gates.md](../foundation/phase_gates.md) 的 `B-1 ~ B-5` 逐条核对
- 运行 `python3 -m unittest discover -s tests -v`
- 运行 `python3 scripts/run_phase_b_gate.py`
- 审阅 [schema.py](../../mind/kernel/schema.py)、[store.py](../../mind/kernel/store.py)、[integrity.py](../../mind/kernel/integrity.py)、[replay.py](../../mind/kernel/replay.py) 与 [golden_episode_set.py](../../mind/fixtures/golden_episode_set.py)

## 1. 结论

Phase B 本次验收结论：`PASS`

判定依据：

- `B-1 ~ B-5` 五项 MUST-PASS 指标全部通过
- 本地最小记忆内核已具备 append-only、source trace、version chain、replay fidelity 四个底座能力
- 未发现阻断阶段 C Primitive API 开发的结构性缺口

## 2. Gate 结果

| Gate | 阈值 | 结果 | 结论 |
| --- | --- | --- | --- |
| `B-1` | GoldenEpisodeSet v1 上 round-trip `100%` 一致 | `142/142` | `PASS` |
| `B-2` | `SourceTraceCoverage = 1.0` | `1.00` | `PASS` |
| `B-3` | dangling refs `= 0`，cycle `= 0`，version issues `= 0` | `0 / 0 / 0` | `PASS` |
| `B-4` | `20/20` golden episode replay 完全一致 | `20/20` | `PASS` |
| `B-5` | 必填 metadata 覆盖率 `= 1.0` | `1.00` | `PASS` |

补充观察：

- `8/8` 核心对象类型样例可被 store 接受并通过 validator
- gate 脚本已将 `B-1 ~ B-5` 明确映射为可执行输出，避免 gate 逻辑散落在说明文字中

## 3. 逐条审计

### `B-1` Ingest / Read round-trip 准确率

门槛定义见 [phase_gates.md](../foundation/phase_gates.md)。

核对结果：

- [golden_episode_set.py](../../mind/fixtures/golden_episode_set.py) 生成 `20` 个 golden episodes
- [phase_b.py](../../mind/kernel/phase_b.py) 对 GoldenEpisodeSet v1 的全部对象执行写入后读取比对
- 本次结果为 `142/142` 对象 round-trip 一致

审计意见：

- 当前存储层对对象 JSON 编解码保持稳定
- `read_object(object_id, version)` 已具备版本精确读取能力，可直接服务阶段 C primitive contract

判定：

- `B-1 = PASS`

### `B-2` `SourceTraceCoverage`

门槛定义见 [phase_gates.md](../foundation/phase_gates.md)。

核对结果：

- [schema.py](../../mind/kernel/schema.py) 强制 `RawRecord` 之外的所有对象具有非空 `source_refs`
- [store.py](../../mind/kernel/store.py) 在写入时拒绝 dangling `source_refs`
- [integrity.py](../../mind/kernel/integrity.py) 对 trace 覆盖率执行审计
- 本次结果为 `1.00`

审计意见：

- trace 规则同时体现在 schema、写入路径和离线 audit 三层，而不只是测试期约定
- 该约束足以支撑后续 primitive 写回和 episode replay 的可追溯性要求

判定：

- `B-2 = PASS`

### `B-3` 版本图完整性

门槛定义见 [phase_gates.md](../foundation/phase_gates.md)。

核对结果：

- [store.py](../../mind/kernel/store.py) 强制版本连续增长，拒绝跳号写入
- [integrity.py](../../mind/kernel/integrity.py) 审计 dangling refs、trace cycle、version chain gap
- [test_phase_b_gate.py](../../tests/test_phase_b_gate.py) 覆盖了 dangling ref 与非连续版本的拒绝场景
- 本次结果为：
  - dangling refs `= 0`
  - cycles `= 0`
  - version chain issues `= 0`

审计意见：

- 当前实现已满足“append-only 且无 silent overwrite”的阶段目标
- 版本图审计仍然是最小版本，后续如果引入显式父版本字段，可进一步增强历史分叉表达

判定：

- `B-3 = PASS`

### `B-4` Replay fidelity

门槛定义见 [phase_gates.md](../foundation/phase_gates.md)。

核对结果：

- [replay.py](../../mind/kernel/replay.py) 使用稳定 canonical JSON + SHA256 计算事件顺序 hash
- [phase_b.py](../../mind/kernel/phase_b.py) 对 `20/20` golden episodes 执行 replay 比对
- 本次结果为 `20/20`

审计意见：

- 当前 replay fidelity 依赖 `RawRecord.metadata.timestamp_order` 排序，这符合阶段 B 的最小设计
- 后续若引入跨 source 的复杂事件流，需要补充更强的 ordering contract

判定：

- `B-4 = PASS`

### `B-5` 必填 metadata 覆盖率

门槛定义见 [phase_gates.md](../foundation/phase_gates.md)。

核对结果：

- [schema.py](../../mind/kernel/schema.py) 冻结了 `8` 类对象各自的必填 metadata 字段
- [integrity.py](../../mind/kernel/integrity.py) 对所有对象执行 validator 并统计覆盖率
- 本次结果为 `1.00`

审计意见：

- metadata 完整性已经从“文档要求”转成“可执行校验”
- 阶段 C 可以直接在此基础上构建 primitive request/response contract tests

判定：

- `B-5 = PASS`

## 4. 阻断项与发现

阻断项：

- 未发现阻断 Phase B 通过的硬性问题

主要发现：

- 当前 Phase B 已形成一套闭环：`schema validator -> append-only store -> integrity audit -> replay check -> gate report`
- GoldenEpisodeSet v1 同时覆盖成功、失败、tool call、retry、summary revision 等基础 episode 形态
- Phase B gate 已从“手工解释”收束为 [phase_b.py](../../mind/kernel/phase_b.py) 和 [run_phase_b_gate.py](../../scripts/run_phase_b_gate.py) 的可复用评估入口

## 5. 非阻断风险

- 当前存储后端是单文件 SQLite，适合阶段 B 的正确性基线，但还不是并发写入场景的最终答案
- replay fidelity 依赖固定的 `timestamp_order` 元数据；若未来支持更复杂的 partial order，需要升级排序与哈希协议
- integrity check 当前只检查 `source_refs` 图，不检查 `LinkEdge.content.src_id/dst_id` 是否存在；如果阶段 C primitive 开始大量生成关系边，这一项应补进 audit
- `WorkspaceView` 虽可持久化，但当前 gate 不涉及 workspace selection 或 slot discipline，这些要到阶段 D 再正式验收

## 6. 质量观察

1. **底座边界干净**：Phase B 只实现 schema、store、integrity、replay，不提前掺入 retrieval、policy、workspace builder。
2. **错误路径已具备最小防线**：danging refs 与非连续版本会在写入时被拒绝，避免问题滞后到离线审计阶段才暴露。
3. **gate 结果可复用**：测试和脚本都改为复用统一的 [phase_b.py](../../mind/kernel/phase_b.py)，后续扩展指标时不会四处复制逻辑。
4. **fixtures 具有阶段适配性**：GoldenEpisodeSet v1 数量不大，但结构分布足以支持阶段 C 的 primitive smoke / contract 测试起步。

## 7. 最终结论

本次验收判定：

`Phase B = PASS`

可进入下一阶段：

- 阶段 C：Primitive API 完成

建议阶段 C 的直接起步项：

- 为 `write_raw / read / retrieve / summarize / link / reflect / reorganize_simple` 定义请求与响应 schema
- 为 primitive 调用补结构化日志
- 实现预算约束、失败原子性与 contract tests
