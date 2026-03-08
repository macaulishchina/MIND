# 阶段验收与 Phase Gates

## 1. 这份文档的作用

这份文档只回答一个问题：

**某个阶段什么时候算真正完成，可以放心进入下一阶段。**

这里不再使用“差不多完成”“基本可用”这种描述。

每个阶段都定义为一个 `phase gate`：

- 每条指标都是必要条件
- 该阶段全部指标通过，才构成进入下一阶段的充分条件
- 任意一条不通过，该阶段就不算完成

这份文档和 [设计拆解与前期实施指南](../design/design_breakdown.md) 的分工是：

- 主文档：解释为什么这样设计
- 本文档：定义怎么验收

---

## 2. Gate 规则

## 2.1 总规则

一个阶段 `S_n` 被判定为 `PASS`，当且仅当：

- 该阶段所有 `MUST-PASS` 指标全部通过
- 所有指标都已经有明确的验证方法和记录
- 该阶段产物已经被冻结为可引用版本

## 2.2 为什么这些指标可以视为“充分必要”

这里的“充分必要”不是数学证明意义上的绝对真理，而是项目治理意义上的 gate 设计：

- 必要：下一阶段确实依赖这些条件
- 充分：这些条件 together 覆盖了下一阶段启动所需的全部前置依赖

换句话说，本文件定义的是：

**MIND 项目内部的阶段准入条件。**

## 2.3 验收记录要求

每次 gate 验收都必须产出一份记录，至少包含：

- 验收日期
- 验收对象版本或 commit
- 使用的数据集 / fixture 版本
- 每条指标结果
- 结论：`PASS / FAIL`

---

## 3. 共享定义

## 3.1 共享数据集 / 工件

为了让量化指标可落地，后续阶段必须维护下面这些版本化工件。

| 工件 | 最小要求 | 用途 |
| --- | --- | --- |
| `GoldenEpisodeSet v1` | 至少 `20` 个完整 episode；覆盖成功、失败、工具调用、重试 | 验证存储、回放、trace |
| `PrimitiveGoldenCalls v1` | 至少 `200` 个 primitive 调用样例；覆盖正常、异常、超预算、回滚 | 验证 primitive API |
| `RetrievalBenchmark v1` | 至少 `100` 个查询；每个查询有标注相关对象和 gold facts | 验证检索与 workspace |
| `EpisodeAnswerBench v1` | 至少 `100` 个单回答评测样例；每个样例含任务 rubric、gold facts、hard constraints、gold memory refs、baseline 成本 | 验证单次回答质量与 memory contribution |
| `LongHorizonDev v1` | 至少 `30` 条任务序列；每条序列 `5~10` 步 | 验证 replay / promotion / archive |
| `LongHorizonEval v1` | 至少 `50` 条任务序列；与 dev 集分离 | 最终比较 MIND 与 baseline |

## 3.2 共享指标

### `SourceTraceCoverage`

定义：

`有有效 source_refs 的派生对象数 / 全部派生对象数`

要求：

- 有效 source ref 指向存在对象
- 引用链无悬空

### `ReplayLift`

定义：

`Top-decile replayed 对象的未来复用率 / 随机 decile 对象的未来复用率`

### `PromotionPrecision@10`

定义：

被 `promote` 的对象中，在后续 `10` 个任务内：

- 没被回滚或废弃
- 至少被复用 `1` 次

的比例。

### `PollutionRate`

定义：

`在观察窗口内被标记为 invalid / contradicted / deprecated 的新派生对象数 / 新派生对象总数`

### `TaskCompletionScore`

定义：

单次回答是否完成任务目标的归一化分数，范围 `[0, 1]`。

建议：

- 可判定任务用精确匹配、单元测试、执行结果或规则校验
- 开放任务用 rubric judge 打分并归一化
- 允许 `0 / 0.5 / 1` 这样的粗粒度离散值，但不强制

### `ConstraintSatisfaction`

定义：

`满足的 hard constraints 数 / 全部 hard constraints 数`

说明：

- hard constraints 包括格式要求、禁止项、工具使用边界、长度上限、输出字段完整性等
- 这是任务遵从性指标，不等同于事实正确性

### `AnswerFaithfulness`

定义：

`有明确证据支持的关键回答 claim 数 / 全部关键回答 claim 数`

说明：

- 证据可来自 prompt 已知信息、工具结果、`read` 对象或 workspace 支撑对象
- 该指标主要惩罚“答对了但依据不对”或“夹带无依据断言”

### `NeededMemoryRecall@20`

定义：

`top-20 retrieved candidates 中命中的 gold memory refs 数 / 全部 gold memory refs 数`

说明：

- 用于衡量检索是否把真正需要的记忆找回来
- 如果某任务不依赖历史记忆，则该指标记为 not-applicable

### `WorkspaceSupportPrecision`

定义：

`实际支撑最终回答的 workspace slots 数 / workspace 全部 slots 数`

说明：

- 该指标衡量 workspace 是否装入了真正有用的信息，而不是只会堆候选
- 支撑关系由 trace 或审计标注给出

### `AnswerTraceSupport`

定义：

`可追溯到 read objects / workspace slots 的关键回答 claim 数 / 全部关键回答 claim 数`

说明：

- 它评估的是“回答是否真的使用了记忆”，而不是只看最终答案对不对
- 该指标对记忆算法优化比裸 answer score 更有诊断价值

### `WritebackTraceCoverage`

定义：

`本次 episode 新增派生对象中具有有效 source_refs 的对象数 / 全部新增派生对象数`

### `ImmediatePollutionProxy`

定义：

`本次 episode 新增派生对象中，被即时 validator、冲突检查或审计标为低可信 / 矛盾 / 空洞的对象数 / 全部新增派生对象数`

说明：

- 它是 `PollutionRate` 的短期代理指标
- 用于在未来复用结果尚未观察到前，先给 writeback 一个即时质量信号

### `WallClockLatency`

定义：

从任务开始处理到最终回答完成的端到端耗时。

说明：

- 必须在冻结的评测环境下采集：同模型、同 provider、同硬件层级、同网络区域、同并发条件
- 默认同时报告 `p50` 与 `p95`
- 它适合衡量真实用户体感，但跨平台可比性较差

### `LatencyRatio`

定义：

`WallClockLatency_p50(system) / WallClockLatency_p50(baseline)`

说明：

- baseline 必须在同一环境下运行
- 如果平台波动较大，也应同时报告 `p95`
- 它是“真实速度”指标，而不是算法复杂度指标

### `ReadCountRatio`

定义：

`(read objects 数 + expand 操作数) / baseline 对应值`

说明：

- 它近似衡量在线阶段的显式 memory access 开销
- 相比 wall-clock，它更接近算法层的工作量代理

### `GenerationTokenRatio`

定义：

`本次回答 output tokens / baseline output tokens`

说明：

- 它用于惩罚“为了提高正确率而极端拉长回答”的策略
- 该指标和 `ContextCostRatio` 一起覆盖 online 阶段的主要 token 开销

### `TimeBudgetHitRate`

定义：

`在任务规定时间预算内完成回答的 episode 数 / 全部 episode 数`

说明：

- 每类任务应显式配置自己的时间预算，而不是全局统一一个秒数
- 它比单一平均延迟更接近产品约束，因为用户往往关心是否超时而不只是平均速度

### `OnlineCostRatio`

定义：

`0.40 * ContextCostRatio + 0.15 * GenerationTokenRatio + 0.20 * ReadCountRatio + 0.25 * LatencyRatio`

说明：

- 其中各 ratio 都相对同任务上的固定 baseline 计算
- 默认 baseline 使用 `raw-top20 context`
- 该指标同时吸收了输入 token、输出 token、memory access 工作量与真实 wall-clock 延迟
- 如果需要跨平台比较，应优先比较各 ratio 与 trace，不要只比较绝对秒数

### `CostEfficiencyScore`

定义：

`min(1, 1 / OnlineCostRatio) * TimeBudgetHitRate`

说明：

- baseline 成本对应分数 `1.0`
- 比 baseline 更省时不再继续加分，避免系统为省成本牺牲正确性
- `TimeBudgetHitRate` 用于把“是否在可接受时间内完成”显式并入效率评分

### `AnswerQualityScore (AQS)`

定义：

`AQS = 0.45 * TaskCompletionScore + 0.20 * ConstraintSatisfaction + 0.20 * GoldFactCoverage + 0.15 * AnswerFaithfulness`

说明：

- `AQS` 只回答“这次任务答得好不好”
- 它故意不把记忆检索质量混进来，以便和 memory use 分开诊断

### `MemoryUseScore (MUS)`

定义：

`MUS = 0.40 * NeededMemoryRecall@20 + 0.30 * WorkspaceSupportPrecision + 0.30 * AnswerTraceSupport`

说明：

- `MUS` 回答的是“记忆系统是否把正确的信息找到、放对、并真正用上”
- 它是检索器、workspace builder、read policy 的核心优化目标

### `WritebackHealthScore (WHS)`

定义：

`WHS = 0.60 * WritebackTraceCoverage + 0.40 * (1 - ImmediatePollutionProxy)`

说明：

- `WHS` 只在发生 writeback 的任务上计算
- 如果该任务不要求 writeback，则该项记为 not-applicable，并在总分中做权重重归一化

### `EpisodeUtilityScore (EUS)`

定义：

`EUS = 0.45 * AQS + 0.25 * MUS + 0.15 * WHS + 0.15 * CostEfficiencyScore`

说明：

- `EUS` 是单次回答级别的密集代理指标，用于开发期快速迭代
- 若 `MUS` 或 `WHS` 在某任务上 not-applicable，则对剩余项做权重重归一化
- `EUS` 不是最终目标；它服务于局部调参与归因，最终仍由长程 `PUS` 验证

### `PrimaryUtilityScore (PUS)`

为了避免阶段 F 和 G 同时比较太多维度，统一使用：

`PUS = 0.55 * TaskSuccessRate + 0.15 * GoldFactCoverage + 0.10 * ReuseRate - 0.10 * ContextCostRatio - 0.05 * MaintenanceCostRatio - 0.05 * PollutionRate`

说明：

- 所有项归一化到 `[0, 1]`
- `ContextCostRatio` 以 `raw-top20 context baseline = 1.0`
- `MaintenanceCostRatio` 以 `no-offline-maintenance baseline = 1.0`

## 3.3 单次回答评估协议

为了让一次回答的评估既能反映回答质量，又能服务记忆算法迭代，阶段 F 之前建议统一按以下流程执行：

1. 为每个评测样例冻结 `task prompt / world-state snapshot / gold facts / hard constraints / gold memory refs / baseline cost`
2. 运行被评系统，完整记录 `retrieve / read / workspace / answer / writeback` trace
3. 先用规则脚本计算可自动验证指标：`TaskCompletionScore`、`ConstraintSatisfaction`、成本、trace 完整性
4. 再对关键回答 claim 做 evidence audit，得到 `GoldFactCoverage`、`AnswerFaithfulness`、`AnswerTraceSupport`
5. 对 retrieved candidates 和 workspace slots 做标注或审计，得到 `NeededMemoryRecall@20` 与 `WorkspaceSupportPrecision`
6. 如果本次任务有 writeback，再计算 `WritebackTraceCoverage` 与 `ImmediatePollutionProxy`
7. 汇总得到 `AQS / MUS / WHS / CostEfficiencyScore / EUS`
8. 所有 episode 结果必须保留子分项，而不是只保留总分

## 3.4 反事实与归因指标

如果目标是优化记忆算法，而不是只优化最终回答文本，则还应记录以下差分指标：

### `MemoryLift`

定义：

`EUS(full system) - EUS(no-memory baseline)`

用途：

- 衡量“这次回答的提升有多少来自记忆系统”

### `WorkspaceLift`

定义：

`EUS(full workspace builder) - EUS(raw-top20 without structured workspace)`

用途：

- 衡量 `WorkspaceView` 是否真的比直接拼候选片段更有价值

### `WritebackForwardLift@5`

定义：

`当前 episode 的 writeback 开启时，后续 5 个相关任务平均 EUS - writeback 关闭时，后续 5 个相关任务平均 EUS`

用途：

- 给本次 writeback 提供延迟信用分配
- 它是连接单次回答评估与长期记忆优化的关键桥梁

## 3.5 设计原则

单次回答评估不应只回答“答得对不对”，还必须回答：

- 对的是不是因为真的找对了记忆
- 找到的记忆是不是被正确组织进 workspace
- 回答中的关键 claim 是否有证据支持
- 这次写回是在改善未来记忆，还是在制造污染
- 成本是否值得

因此，项目中建议同时保留：

- `EUS`：服务开发期快速迭代、局部调参、组件归因
- `PUS`：服务长程比较、阶段 gate、最终系统选择

---

## 4. 阶段依赖链

```mermaid
flowchart LR
    A[阶段 A\n系统定义] --> B[阶段 B\n记忆内核]
    B --> C[阶段 C\nPrimitive API]
    C --> D[阶段 D\n检索与 Workspace]
    D --> E[阶段 E\n反思 / Replay / Promotion]
    E --> F[阶段 F\n评测与 Baseline]
    F --> G[阶段 G\n策略优化]
```

依赖关系说明：

- B 依赖 A 的对象模型与 primitive 合约
- C 依赖 B 的稳定存储和 trace
- D 依赖 C 的统一 API
- E 依赖 D 的可用 workspace 和检索
- F 依赖 E 的完整成长闭环
- G 依赖 F 已经证明系统“值得优化”

---

## 5. Phase Gates

## 阶段 A Gate：系统定义完成

### 阶段目标

把“概念设计”冻结成可以直接驱动实现的正式规范。

### MUST-PASS 指标

| Gate ID | 指标 | 阈值 | 验证方式 |
| --- | --- | --- | --- |
| `A-1` | `SPEC` 必备章节完整度 | `7/7` 必备章节存在：`memory world / object schema / primitive catalog / workspace view / utility objective / online loop / offline loop` | 文档检查 |
| `A-2` | 对象模型完整度 | `8/8` 必备对象类型都定义；每个对象 `10/10` 必填字段齐全 | schema checklist |
| `A-3` | Primitive 合约完整度 | `7/7` 必备 primitives 都定义 `input / output / side effects / failure modes / budget effects` 五类信息 | contract checklist |
| `A-4` | 强制未决项数量 | 必备章节中的 `TBD / TODO / ??? = 0` | 文档扫描 |
| `A-5` | 端到端示例覆盖 | 至少 `3` 个 episode 被完整映射到 `state / action / observation / reward` | 示例审阅 |

### 通过结论

当 `A-1 ~ A-5` 全部通过时，阶段 A `PASS`。  
此时可以保证阶段 B 开发不会因为规范空洞而反复返工。

---

## 阶段 B Gate：最小记忆内核完成

### 阶段目标

得到一个可追溯、可回放、可版本化的记忆底座。

### MUST-PASS 指标

| Gate ID | 指标 | 阈值 | 验证方式 |
| --- | --- | --- | --- |
| `B-1` | Ingest / Read round-trip 准确率 | 在 `GoldenEpisodeSet v1` 上 `100%` 一致；事件顺序 hash 完全匹配 | 回放脚本 |
| `B-2` | `SourceTraceCoverage` | `100%` | trace audit |
| `B-3` | 版本图完整性 | dangling refs `= 0`，cycle `= 0` | integrity check |
| `B-4` | Replay fidelity | `20/20` 个 golden episode 回放结果与原日志完全一致 | replay diff |
| `B-5` | 必填 metadata 覆盖率 | `100%` 对象具有 schema 规定的必填字段 | schema validator |

### 通过结论

当 `B-1 ~ B-5` 全部通过时，阶段 B `PASS`。  
此时阶段 C 可以把 primitive 放在一个稳定的状态底座上执行。

---

## 阶段 C Gate：Primitive API 完成

### 阶段目标

让 Agent 对记忆世界的最小操作真正成为稳定接口。

### MUST-PASS 指标

| Gate ID | 指标 | 阈值 | 验证方式 |
| --- | --- | --- | --- |
| `C-1` | Primitive 实现覆盖 | `7/7` 必需 primitives 可调用：`write_raw / read / retrieve / summarize / link / reflect / reorganize_simple` | API smoke test |
| `C-2` | 请求 / 响应 schema 合规率 | 在 `PrimitiveGoldenCalls v1` 上 `200/200` 调用 schema 校验通过 | contract tests |
| `C-3` | 结构化日志覆盖率 | `100%` primitive 调用都有 `actor / timestamp / target_ids / cost / outcome` | log audit |
| `C-4` | 预算约束执行率 | `50/50` 超预算调用被拒绝，且返回明确错误码 | fault tests |
| `C-5` | 失败原子性 | `50/50` 注入失败场景无 partial write | rollback tests |

### 通过结论

当 `C-1 ~ C-5` 全部通过时，阶段 C `PASS`。  
此时阶段 D 可以安全地构建 retrieval 和 workspace，而不用担心 API 行为不稳定。

---

## 阶段 D Gate：检索与 Workspace 完成

### 阶段目标

证明系统不仅能存，还能以受控成本组织可用记忆。

### MUST-PASS 指标

| Gate ID | 指标 | 阈值 | 验证方式 |
| --- | --- | --- | --- |
| `D-1` | 检索模式覆盖 | `3/3` 模式可用：`keyword / vector / time-window` | retrieval smoke test |
| `D-2` | Candidate recall@20 | 在 `RetrievalBenchmark v1` 上 `>= 0.85` | benchmark eval |
| `D-3` | Workspace gold-fact coverage | 在 `RetrievalBenchmark v1` 上 `>= 0.80` | workspace audit |
| `D-4` | Workspace 槽位纪律 | `100%` workspace 满足 `slot_count <= K`，且 `100%` slot 有 source refs | builder validator |
| `D-5` | 成本收益门槛 | 相比 `raw-top20 baseline`，median token cost `<= 0.60x`，且 task success drop `<= 5` 个百分点 | A/B benchmark |

### 通过结论

当 `D-1 ~ D-5` 全部通过时，阶段 D `PASS`。  
此时阶段 E 可以基于稳定可用的 workspace 做 replay、反思和 promotion，而不是在噪声上下文上做重组。

---

## 阶段 E Gate：反思、离线维护与轻量重组完成

### 阶段目标

证明系统开始具有“会成长”的特征，而不只是“会积累”。

### MUST-PASS 指标

| Gate ID | 指标 | 阈值 | 验证方式 |
| --- | --- | --- | --- |
| `E-1` | 新派生对象 trace 完整率 | 反思、summary、schema、promotion 对象的 `SourceTraceCoverage = 100%` | trace audit |
| `E-2` | `SchemaValidationPrecision` | 可验证 schema / link / synthesis 对象中，证据支持率 `>= 0.85` | evidence audit |
| `E-3` | `ReplayLift` | 在 `LongHorizonDev v1` 上 `>= 1.5` | replay analysis |
| `E-4` | `PromotionPrecision@10` | `>= 0.80` | promotion audit |
| `E-5` | 离线维护净收益 | 开启 offline maintenance 后，`PUS` 相比关闭时提升 `>= 0.05`，且 `PollutionRate` 增幅 `<= 0.02` | A/B dev eval |

### 通过结论

当 `E-1 ~ E-5` 全部通过时，阶段 E `PASS`。  
此时阶段 F 可以把“成长闭环”当成一个真正可评测对象，而不是 still-in-progress 的原型。

---

## 阶段 F Gate：评测与 Baseline 完成

### 阶段目标

证明 MIND 的复杂度在量化上是值得的。

### MUST-PASS 指标

| Gate ID | 指标 | 阈值 | 验证方式 |
| --- | --- | --- | --- |
| `F-1` | 评测集冻结 | `LongHorizonEval v1` 已版本化，所有 run 使用同一 hash | eval manifest |
| `F-2` | Baseline 完整性 | `3/3` baseline 可运行：`no-memory / plain RAG / fixed summary memory`，完成率 `100%` | benchmark runs |
| `F-3` | 统计报告完整性 | 每个系统 `>= 3` 次独立运行，并给出 `95% CI` | eval report |
| `F-4` | 相对 `no-memory` 优势 | `PUS` 提升 `>= 0.10`，且 CI 下界 `> 0` | benchmark comparison |
| `F-5` | 相对 `fixed summary memory` 优势 | `PUS` 提升 `>= 0.05`，且 CI 下界 `> 0` | benchmark comparison |
| `F-6` | 相对 `plain RAG` 非劣 | `PUS` 差值 `>= -0.02` | benchmark comparison |
| `F-7` | 关键组件可归因 | 去掉 `workspace` 或 `offline maintenance` 任一组件时，`PUS` 下降 `>= 0.03`；否则该组件必须在进入 G 前被删除或重做 | ablation |

### 通过结论

当 `F-1 ~ F-7` 全部通过时，阶段 F `PASS`。  
此时阶段 G 才有意义，因为系统已经被证明至少具备“值得继续优化”的基础价值。

---

## 阶段 G Gate：策略优化完成

### 阶段目标

证明系统不仅结构合理，而且已经学会比固定规则更好地使用记忆。

### MUST-PASS 指标

| Gate ID | 指标 | 阈值 | 验证方式 |
| --- | --- | --- | --- |
| `G-1` | 同预算下策略收益 | 在 `LongHorizonEval v1` 上，优化策略相对固定规则策略 `PUS` 提升 `>= 0.05` | benchmark comparison |
| `G-2` | 预算偏差 | token / storage / maintenance 总成本偏差 `<= 5%` | cost report |
| `G-3` | 泛化覆盖 | 改进同时出现在 `>= 2` 个任务家族上 | per-family eval |
| `G-4` | 污染控制 | `PollutionRate` 相比规则策略增幅 `<= 0.02` | audit report |
| `G-5` | 统计稳定性 | `>= 3` 次独立运行，且 `PUS` 提升的 `95% CI` 下界 `> 0` | eval report |

### 通过结论

当 `G-1 ~ G-5` 全部通过时，阶段 G `PASS`。  
这意味着 MIND 已经从“有成长闭环”进入“闭环本身可被优化”的阶段。

---

## 6. 实施建议

为了让这份 gate 文档真正可用，建议后续按下面的顺序补齐：

1. 先在阶段 A 中固定工件名字和目录
2. 再在阶段 B 中引入 `GoldenEpisodeSet v1`
3. 再在阶段 C 中建立 primitive golden call 集
4. 再在阶段 D/F 中把 benchmark 和报告模板冻结
5. 每次阶段验收都把结果写入独立记录，而不是只口头判断

如果未来要扩展指标，原则是：

- 优先扩展共享工件和共享指标
- 不要让单阶段 gate 混入下一阶段才需要的指标
- gate 变更必须版本化
