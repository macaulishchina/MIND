# Phase A 验收报告

验收日期：`2026-03-08`

验收对象：

- [spec.md](../foundation/spec.md)
- [phase_gates.md](../foundation/phase_gates.md)

验收范围：

- `A-1` `SPEC` 必备章节完整度
- `A-2` 对象模型完整度
- `A-3` Primitive 合约完整度
- `A-4` 强制未决项数量
- `A-5` 端到端示例覆盖

验收方法：

- 按 [phase_gates.md](../foundation/phase_gates.md#L421) 的 `A-1 ~ A-5` 逐条核对
- 对 [spec.md](../foundation/spec.md) 做章节审计、字段审计、contract 审计
- 对必备章节执行 `TBD / TODO / ???` 文本扫描
- 对 3 个端到端 episode 做结构化审阅，确认 `state / action / observation / reward` 四类信息齐全

## 1. 结论

Phase A 本次验收结论：`PASS`

判定依据：

- `A-1 ~ A-5` 五项 MUST-PASS 指标全部通过
- 未发现阻断阶段 B 启动的规范空洞
- 未发现必备章节中的 `TBD / TODO / ???`

## 2. Gate 结果

| Gate | 阈值 | 结果 | 结论 |
| --- | --- | --- | --- |
| `A-1` | `7/7` 必备章节存在 | `7/7` | `PASS` |
| `A-2` | `8/8` 必备对象类型定义齐全；每对象 `10/10` 必填字段齐全 | 满足 | `PASS` |
| `A-3` | `7/7` 必备 primitives 都定义五类 contract 信息 | `7/7` | `PASS` |
| `A-4` | 必备章节中的 `TBD / TODO / ??? = 0` | `0` | `PASS` |
| `A-5` | 至少 `3` 个 episode 完整映射到 `state / action / observation / reward` | `3/3` | `PASS` |

## 3. 逐条审计

### `A-1` SPEC 必备章节完整度

门槛定义见 [phase_gates.md](../foundation/phase_gates.md#L431)。

核对结果：

- `memory world` 存在于 [spec.md](../foundation/spec.md#L51)
- `object schema` 存在于 [spec.md](../foundation/spec.md#L109)
- `primitive catalog` 存在于 [spec.md](../foundation/spec.md#L422)
- `workspace view` 存在于 [spec.md](../foundation/spec.md#L779)
- `utility objective` 存在于 [spec.md](../foundation/spec.md#L873)
- `online loop` 存在于 [spec.md](../foundation/spec.md#L910)
- `offline loop` 存在于 [spec.md](../foundation/spec.md#L952)

判定：

- 必备章节 `7/7` 均存在
- `A-1 = PASS`

### `A-2` 对象模型完整度

门槛定义见 [phase_gates.md](../foundation/phase_gates.md#L432)。

核对结果：

- 核心对象类型 `8` 类均已冻结于 [spec.md](../foundation/spec.md#L120)
- 统一 `10` 个必填字段定义齐备于 [spec.md](../foundation/spec.md#L141)
- 各对象类型特定字段已逐项给出：
  - `RawRecord` [spec.md](../foundation/spec.md#L168)
  - `TaskEpisode` [spec.md](../foundation/spec.md#L176)
  - `SummaryNote` [spec.md](../foundation/spec.md#L186)
  - `ReflectionNote` [spec.md](../foundation/spec.md#L194)
  - `EntityNode` [spec.md](../foundation/spec.md#L202)
  - `LinkEdge` [spec.md](../foundation/spec.md#L210)
  - `WorkspaceView` [spec.md](../foundation/spec.md#L223)
  - `SchemaNote` [spec.md](../foundation/spec.md#L232)

审计意见：

- `10/10` 必填字段以统一 schema 形式适用于全部对象
- `8/8` 核心对象均有明确的类型特定约束
- 对象判定原则与冲突消解规则已补全，有助于避免实现期歧义，见 [spec.md](../foundation/spec.md#L241) 与 [spec.md](../foundation/spec.md#L382)

判定：

- `A-2 = PASS`

### `A-3` Primitive 合约完整度

门槛定义见 [phase_gates.md](../foundation/phase_gates.md#L433)。

核对结果：

- `7` 个必备 primitive 已冻结于 [spec.md](../foundation/spec.md#L470)
- contract 模板五要素定义齐备于 [spec.md](../foundation/spec.md#L558)
- 各 primitive 均具备 `input / output / side_effects / failure_modes / budget_effects`
  - `write_raw` [spec.md](../foundation/spec.md#L570)
  - `read` [spec.md](../foundation/spec.md#L599)
  - `retrieve` [spec.md](../foundation/spec.md#L623)
  - `summarize` [spec.md](../foundation/spec.md#L653)
  - `link` [spec.md](../foundation/spec.md#L680)
  - `reflect` [spec.md](../foundation/spec.md#L707)
  - `reorganize_simple` [spec.md](../foundation/spec.md#L732)

审计意见：

- primitive 的语义边界原则、必要性与最小性标准也已显式定义，降低了后续接口漂移风险，见 [spec.md](../foundation/spec.md#L434) 与 [spec.md](../foundation/spec.md#L452)

判定：

- `A-3 = PASS`

### `A-4` 强制未决项数量

门槛定义见 [phase_gates.md](../foundation/phase_gates.md#L434)。

核对结果：

- 对 [spec.md](../foundation/spec.md) 执行 `TBD|TODO|???` 扫描，未发现匹配项

审计意见：

- 当前必备章节中不存在显式未决占位符
- 规范文本已达到可引用、可冻结状态

判定：

- `A-4 = PASS`

### `A-5` 端到端示例覆盖

门槛定义见 [phase_gates.md](../foundation/phase_gates.md#L435)。

核对结果：

- 示例 1：一次成功的任务回忆，包含 `state / observation / action / reward` 四部分，见 [spec.md](../foundation/spec.md#L1016)
- 示例 2：一次失败后的反思与整理，包含 `state / observation / action / reward` 四部分，见 [spec.md](../foundation/spec.md#L1048)
- 示例 3：跨 episode schema 晋升，包含 `state / observation / action / reward` 四部分，见 [spec.md](../foundation/spec.md#L1077)

审计意见：

- `3/3` 示例均满足 gate 要求的结构映射
- 示例覆盖了成功复用、失败反思、跨 episode schema 晋升三种关键情形

判定：

- `A-5 = PASS`

## 4. 阻断项与发现

阻断项：

- 未发现阻断 Phase A 通过的硬性问题

主要发现：

- 规范对对象、primitive、workspace、utility、online/offline loop 已形成闭环，能够直接驱动阶段 B 的最小实现
- 文档内部此前的对象数计数不一致问题已消除，当前 `spec.md` 与 `phase_gates.md` 对 `8/8` 对象类型定义保持一致

## 5. 非阻断风险

- 当前验收基于文档审计，不包含运行时 schema validator、contract tests 或 replay 脚本；这些属于阶段 B/C 的实现验收内容，不影响本次 Phase A gate
- 端到端 episode 示例满足 gate，但仍属于说明性样例，不等同于后续 benchmark 工件
- 后续若继续修改 [spec.md](../foundation/spec.md) 或 [phase_gates.md](../foundation/phase_gates.md)，应重新执行本报告中的 `A-1 ~ A-5` 审计

## 5.1 后续阶段需关注的具体风险点

1. **`reorganize_simple` 的边界模糊性**：spec 自身已承认它是"最不纯"的 primitive，聚合了 `archive / deprecate / reprioritize / synthesize_schema` 四种子操作（见 [spec.md](../foundation/spec.md#L549)）。进入阶段 C 实现时，需尽早为每个子操作定义独立的测试用例和 failure mode，避免在一个 primitive 内隐藏过多策略逻辑。
2. **`WorkspaceView` 的 `selection_policy` 未具体定义**：阶段 A 正确地选择了"只冻结接口不冻结算法"，但阶段 D 需要明确至少一个 baseline selection policy 才能验证 gate。
3. **Promotion criteria 尚为软性描述**：§7.5 定义了 `reuse_count >= 2` 等准入条件（见 [spec.md](../foundation/spec.md#L989)），但数值阈值和证据校验流程需在阶段 E 前冻结为可自动化检查的规则。
4. **成本指标的 baseline 尚待具体化**：`ContextCostRatio`、`MaintenanceCostRatio` 的 baseline 定义为 `raw-top20` 和 `no-offline-maintenance`，阶段 F 需要在冻结的评测环境下产出具体 baseline 数值。
5. **示例 3 的 observation-action gap**：示例 3（跨 episode schema 晋升）的 observation 中提到"已满足 promotion criteria"，但 action 使用的是 `reorganize_simple(synthesize_schema)` 而非显式 promote 决策流程。这在阶段 A 是合理的（promote 不是独立 primitive），但阶段 E 需要为 promotion 决策链路补充可审计 trace。

## 6. 质量观察

1. **语义边界清晰**：每个对象类型和 primitive 都附有正反两面的判定规则（"应判定为"和"不应判定为"）与必要性审核，降低后续开发中的歧义争论。
2. **最小性自觉**：spec 显式列出"暂不单列"的操作清单（§3.2.2）和"不冻结"的实现细节（§0.1），避免过早膨胀。
3. **可追溯性硬约束贯穿全文**：`source_refs` 非空、版本链无悬空、禁止 silent overwrite——这些约束为阶段 B 的 integrity check 提供了清晰目标。
4. **端到端示例覆盖场景互补**：成功复用（online loop 主路径）、失败反思（online + 写回）、schema 晋升（offline loop 主路径），三者合力覆盖了系统的核心运行模式。
5. **Primitive 合约的粒度控制得当**：input/output 给出了字段级定义，failure_modes 给出了可枚举的错误类别，budget_effects 给出了成本维度——这三层信息足以驱动阶段 C 的 contract test 编写。

## 7. 最终结论

本次验收判定：

`Phase A = PASS`

可进入下一阶段：

- 阶段 B：最小记忆内核实现

建议阶段 B 的直接起步项：

- append-only 存储
- source trace
- version graph
- object validator
