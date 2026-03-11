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

补充约束：

- 每个阶段的 gate 指标条数不设固定模板
- 指标数量只服从阶段边界、风险面和下一阶段的前置依赖
- 如果某阶段的阻断风险无法被当前指标完整覆盖，就必须继续补指标，而不是为了形式整齐停在固定条数

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

补充说明：

- A ~ G 的通过记录按各自验收当时冻结的版本生效
- 若项目在更后阶段新增控制面、治理接口或新的冻结约束，应以 addendum 形式补入，不自动推翻历史 `PASS`
- 若 addendum 暴露出旧层需要补强的实现卫生问题，默认以 regression hardening 落地，而不是直接回写成 A ~ G 的新 formal gate，除非原阶段目标本身被证明定义错误

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
| `MindCliScenarioSet v1` | 至少 `25` 个 CLI 场景；覆盖 `help / primitive / access / offline / governance / gate / report / demo` | 验证 Phase J 的统一命令行入口 |
| `UserStateScenarioSet v1` | 至少 `30` 个场景；覆盖 `principal / tenant / session / conversation / policy` | 验证产品化阶段的用户状态与执行策略边界 |
| `ProductTransportScenarioSet v1` | 至少 `40` 个场景；覆盖 `REST / MCP / product CLI` 的核心行为一致性 | 验证产品化阶段的统一应用服务与 transport 复用 |
| `DeploymentSmokeSuite v1` | 至少 `20` 个部署场景；覆盖 compose、迁移、health、worker 与 provider config | 验证产品化阶段的部署与运行基线 |
| `ProductCliExperienceBench v1` | 至少 `30` 条产品 CLI 流；覆盖 `remember / recall / ask / history / session / status / config` | 验证产品化阶段的最终用户 CLI |
| `CapabilityAdapterBench v1` | 至少 `40` 个能力调用样例；覆盖 `summarize / reflect / answer / offline_reconstruct` 与 `openai / claude / gemini` 兼容接口 | 验证 Phase K 的统一模型能力调用层 |
| `InternalTelemetryBench v1` | 至少 `30` 条内部流程样例；覆盖 `primitive / retrieval / workspace / access / offline / governance` 与状态变更链 | 验证 Phase L 的开发态完备观测 |
| `FrontendExperienceBench v1` | 至少 `20` 条前端体验流；覆盖功能体验、配置、debug 可视化三类入口 | 验证 Phase M 的前端体验层 |
| `ProvenanceGovernanceBench v1` | 至少 `40` 个治理样例；覆盖 `conceal`、`erase_scope`、approval、mixed-source rewrite、artifact cleanup | 验证 Phase H / N 的 provenance 与治理执行 |
| `AccessDepthBench v1` | 至少 `60` 个运行时任务；覆盖 `speed-sensitive / balanced / high-correctness` 三类任务族 | 验证 Phase I 的固定档位与 `auto` 调度 |
| `PersonaProjectionBench v1` | 至少 `40` 组多轮 identity bundle；覆盖自传连续性、偏好 / 价值一致性、治理后更新 | 验证 Phase O 的 persona projection |

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

## 3.6 Governance / Reshape Addendum

以下内容在 Phase G 之后被冻结，用作下一阶段的正式前置约束。

它们不回滚 A ~ G 已经通过的历史 gate，但会约束后续设计和实现。

### 3.6.1 冻结术语

- `provenance`：原始来源主体、来源环境、采集时间和保留策略所在的 control-plane 记录
- `direct provenance`：直接绑定到 `RawRecord` 或外部导入原始对象的 authoritative provenance
- `provenance footprint`：派生或聚合对象对底层 provenance 的聚合摘要，只用于治理 preview / audit
- `support unit`：对象内部最小可治理单元，例如 `claim / slot / facet / edge`
- `conceal`：逻辑不可见、可恢复的治理性遗忘
- `erase`：物理擦除或带 tombstone 的不可恢复删除

### 3.6.2 冻结边界

- provenance 属于 control plane，不属于 `source_refs`
- provenance 不得参与 runtime retrieval / ranking / weighting
- provenance 默认只用于高权限治理接口和审计查看
- offline maintenance 不得替代 provenance-based governance
- 后续实现至少要有最小 capability 边界，哪怕还没有完整产品权限系统

### 3.6.3 冻结的治理流程

普通治理：

`plan -> preview -> execute`

高风险治理：

`plan -> preview -> approve -> execute`

补充约束：

- 任意 `erase` 至少要有 `preview`
- `erase(scope=full)` 必须进入高风险治理流程
- 所有治理动作都必须产出具名审计记录

### 3.6.4 冻结的 mixed-source 重写语义

- mixed-source 派生对象不允许只“删依赖不改内容”
- mixed-source 派生对象也不要求一律整对象失效
- 正式语义是：先移除受影响 evidence / provenance，再按 `support unit` 判定 `retained / rewritten / dropped`
- `support_rule v1` 冻结为 `min_support_count >= 1`
- 父对象必须生成新版本，或在无法保留任何有效单元时显式失效 / 删除

### 3.6.5 冻结的 `erase_scope`

| scope | 含义 |
| --- | --- |
| `memory_world` | 清理对象、版本、lineage、索引与 provenance 本体 |
| `memory_world_plus_artifacts` | 在 `memory_world` 外，再清理缓存、trace、评测 JSON 和自动生成工件 |
| `full` | 在 `memory_world_plus_artifacts` 外，再处理报表副本、人工导出物与外部可读副本 |

默认 `erase_scope` 冻结为：

- `memory_world_plus_artifacts`

### 3.6.6 下一阶段至少要验证的方向

后续正式 gate 至少应覆盖：

- direct provenance 是否完整绑定到底层原始对象
- `conceal` 是否真正把对象从普通 online / offline 路径隔离
- `erase` 是否在声明的 scope 内清理完成
- mixed-source 对象是否按最小治理粒度正确重写
- 治理执行是否完整保留 `plan / preview / approve / execute` 审计链
- 低权限 read / log / report 路径是否不会旁路泄露高敏 provenance

## 3.7 Runtime Access Depth Addendum

以下内容用于约束后续运行时记忆访问深度设计与评测。

### 3.7.1 冻结术语

- `Flash`：极低延迟、极低访问成本的浅层访问档
- `Recall`：默认平衡档
- `Reconstruct`：允许跨片段、跨 episode 重建的深层访问档
- `Reflective`：对用户暴露的第四档名称；规范内部名为 `reflective_access`
- `auto`：可在不同访问档之间升级、降级、跳级的自动调度模式

### 3.7.2 冻结边界

- 访问深度是 runtime policy，不是新 primitive
- `Reflective` / `reflective_access` 不等同于 primitive `reflect`
- 访问深度调节的是 retrieval / read / workspace / verification 的强度，而不是对象真值
- `auto` 可以覆盖执行路径，但不得覆盖用户显式锁定的固定档位

### 3.7.3 后续 benchmark 最少要回答的问题

后续基准要求测试至少应同时回答：

- 固定档位下，回答质量是否达到该场景要求
- 固定档位下，性能和成本是否仍在可接受范围内
- `auto` 是否能根据场景在不同档位之间合理切换
- `auto` 的升级、降级和自由跳级是否都有 trace
- `auto` 是否形成比“永远固定一个档位”更好的质量 / 性能折中

### 3.7.4 后续 formal gate 至少要同时保留两类指标

质量侧至少应保留：

- `TaskCompletionScore`
- `ConstraintSatisfaction`
- `AnswerFaithfulness`
- `GoldFactCoverage` 或等价证据覆盖指标

性能侧至少应保留：

- `WallClockLatency` 或 `LatencyRatio`
- `ContextCostRatio`
- `ReadCountRatio`
- `GenerationTokenRatio` 或等价 token 成本指标

补充约束：

- 运行时访问深度 gate 不得只看质量，不看性能
- 也不得只看性能，不看回答质量
- `auto` 的判断质量不仅取决于最终分数，也取决于档位切换是否稳定、是否可解释

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
    G --> H[阶段 H\nProvenance Foundation]
    H --> I[阶段 I\nRuntime Access Modes]
    I --> J[阶段 J\nUnified CLI Experience]
    J --> K[阶段 K\nLLM Capability Layer]
    K --> L[阶段 L\nDevelopment Telemetry]
    L --> M[阶段 M\nFrontend Experience]
    M --> N[阶段 N\nGovernance / Reshape]
    N --> O[阶段 O\nPersona / Projection]
```

依赖关系说明：

- B 依赖 A 的对象模型与 primitive 合约
- C 依赖 B 的稳定存储和 trace
- D 依赖 C 的统一 API
- E 依赖 D 的可用 workspace 和检索
- F 依赖 E 的完整成长闭环
- G 依赖 F 已经证明系统“值得优化”
- H 依赖 G 之后冻结的 provenance / governance addendum，但不回滚 A ~ G
- I 依赖 H 的 control plane 基础，并把 access depth 做成可评测 runtime policy
- J 依赖 H / I 已有能力稳定，才能把分散入口收敛成统一命令行体验层
- K 依赖 J 已提供统一入口，再把摘要 / 反思 / 回答 / 离线重构统一成可切换模型能力层
- L 依赖 J / K 的统一调用面，才能在不改现有语义的前提下完整采集内部结构变化
- M 依赖 J / K / L 三层稳定，才能把功能体验、配置与 debug 可视化做成前端入口
- N 依赖 H 的 provenance foundation，并在 M 之后再推进更重的治理执行与记忆网络重塑
- O 依赖 H / N 稳定后，才能把人格层从设计问题推进为工程问题

### 4.1 Post-G 扩展阶段建议

为避免把 provenance、runtime access、governance、persona 混成一个超大阶段，后续建议按下面的顺序推进：

- `H / Provenance Foundation`：补齐 direct provenance、provenance ledger、可见性隔离与审计基础
- `I / Runtime Access Modes`：补齐 `Flash / Recall / Reconstruct / Reflective` 与 `auto` 调度 benchmark
- `J / Unified CLI Experience`：设计统一的 `mind` 命令行入口，让所有记忆模块都能通过一套 CLI 体验、测试和调试
- `K / LLM Capability Layer`：统一摘要 / 反思 / 回答 / 离线重构的能力调用接口，并兼容主流模型提供方
- `L / Development Telemetry`：在开发模式下完备采集内部结构和状态变化，为后续可视化提供数据底座
- `M / Frontend Experience`：基于 CLI、能力层和 telemetry 提供前端体验入口、配置入口和 debug 可视化入口
- `N / Governance / Reshape`：实现 `plan / preview / approve / execute`、mixed-source rewrite 与 artifact cleanup
- `O / Persona / Projection`：在治理链稳定后，推进 autobiographical grouping、value schema 与 runtime persona projection

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

## 阶段 H Gate：Provenance Foundation 完成

### 阶段目标

证明系统已经具备 provenance control plane 的最小可用基础：

- direct provenance 能稳定绑定到底层原始对象
- provenance 可以被高权限查看，但不会旁路泄露到普通路径
- `conceal` 能把受影响记忆从普通 online / offline 路径隔离
- 治理执行具备最小审计链

阶段 H 明确**不要求**：

- mixed-source 细粒度 rewrite
- `erase(scope=full)` 的全外部副本清理
- runtime `Flash / Recall / Reconstruct / Reflective` access policy 实现
- persona / projection 实现

### MUST-PASS 指标

| Gate ID | 指标 | 阈值 | 验证方式 |
| --- | --- | --- | --- |
| `H-1` | direct provenance 绑定完整率 | `RawRecord / ImportedRawRecord` 的 authoritative direct provenance 绑定率 `= 100%` | provenance audit |
| `H-2` | authoritative provenance 完整性 | 每个底层原始对象至多存在 `1` 条 authoritative direct provenance；orphan ledger rows `= 0`；高敏字段 schema 校验通过率 `= 100%` | provenance integrity audit |
| `H-3` | 低权限 provenance 读取隔离 | 低权限 `read / retrieve / workspace / report` 路径读取高敏 provenance 的成功率 `= 0` | capability tests |
| `H-4` | 高权限 provenance 摘要收敛 | 高权限 `read_with_provenance` / governance preview `100%` 可返回冻结摘要，同时超范围高敏字段泄露率 `= 0` | privileged-read audit |
| `H-5` | `conceal` 在线隔离有效性 | 被 `conceal` 的对象在普通 online retrieval、read、workspace 构建路径中默认不可见 | online conceal regression |
| `H-6` | `conceal` 离线隔离有效性 | 被 `conceal` 的对象在默认 offline maintenance / replay / promotion 路径中消费率 `= 0`；治理路径仍可 preview | offline conceal regression |
| `H-7` | 治理审计链完整率 | `plan / preview / execute` 审计记录覆盖率 `= 100%`；若出现 `erase(scope=full)`，则必须有 `approve` | governance audit |
| `H-8` | provenance 优化泄露防护 | provenance 字段 `100%` 不参与 retrieval / ranking / weighting；相关回归比较无行为漂移 | ranking isolation regression |

### 通过结论

当 `H-1 ~ H-8` 全部通过时，阶段 H `PASS`。  
此时阶段 I 才能在稳定的 provenance / visibility 基础上推进 runtime access depth，而阶段 J 也才有资格在这个稳定底盘之上收敛统一 CLI 体验入口。

---

## 阶段 I Gate：Runtime Access Modes 完成

### 阶段目标

证明运行时访问深度已经从“概念档位”变成稳定、可 trace、可评测的 runtime policy：

- `Flash / Recall / Reconstruct / Reflective` 固定档位都能独立运行
- `auto` 能在不同任务族之间做出可解释的档位选择
- 档位切换能够在质量、性能、成本之间形成明确折中
- 用户显式锁定档位时，不会被 `auto` 偷偷覆盖

阶段 I 明确**不要求**：

- provenance-based `erase` 扩展或 mixed-source rewrite
- persona / projection 实现
- 新增一套独立于现有 primitives 的“访问深度 primitive”

### MUST-PASS 指标

| Gate ID | 指标 | 阈值 | 验证方式 |
| --- | --- | --- | --- |
| `I-1` | access mode 合约完整度 | `Flash / Recall / Reconstruct / Reflective / auto = 5/5` 全部可调用；mode trace coverage `= 100%` | integration test |
| `I-2` | `Flash` 场景下限 | 在 `AccessDepthBench v1` 的 `speed-sensitive` 任务上，`TimeBudgetHitRate >= 0.95`，且 `ConstraintSatisfaction >= 0.95` | access benchmark |
| `I-3` | `Recall` 场景下限 | 在 `AccessDepthBench v1` 的 `balanced` 任务上，`AQS >= 0.75`，且 `MUS >= 0.65` | access benchmark |
| `I-4` | `Reconstruct` 场景下限 | 在 `AccessDepthBench v1` 的 `high-correctness` 任务上，`AnswerFaithfulness >= 0.95`，且 `GoldFactCoverage >= 0.90` | access benchmark |
| `I-5` | `Reflective` 场景下限 | 在 `AccessDepthBench v1` 的 `high-correctness` 任务上，`AnswerFaithfulness >= 0.97`，`GoldFactCoverage >= 0.92`，且 `ConstraintSatisfaction >= 0.98` | access benchmark |
| `I-6` | `auto` 质量 / 成本前沿 | 在 `AccessDepthBench v1` 上，`auto` 相对各任务族中“先满足该任务族场景下限、再按 `CostEfficiencyScore` 选出的 family-best fixed mode”的 `AQS` 平均降幅 `<= 0.02`，且 `CostEfficiencyScore` 不低于该 family-best fixed mode | frontier comparison |
| `I-7` | `auto` 切换稳定性与可解释性 | `upgrade / downgrade / jump` 三类切换都至少有具名 trace；无理由往返震荡率 `<= 5%`；无原因码切换比例 `= 0` | auto audit |
| `I-8` | 用户锁定档位遵从率 | 用户显式固定 `Flash / Recall / Reconstruct / Reflective` 时，运行轨迹中被 `auto` 覆盖的比例 `= 0` | policy compliance tests |

### 通过结论

当 `I-1 ~ I-8` 全部通过时，阶段 I `PASS`。  
此时 runtime access depth 不再只是设计口号，而成为可比较、可调优、可解释的运行时能力；阶段 J 才有必要在这个稳定 runtime 底盘之上收敛统一体验入口。

---

## 阶段 J Gate：Unified CLI Experience 完成

产品化 addendum：

- 历史上的 Phase J `PASS` 继续有效
- 但如果保留这套统一 CLI 作为开发/验收入口，它的正式命名应迁移到 `mindtest`
- `mind` 这个命名保留给后续产品 CLI
- 这条 addendum 不回滚 Phase J 的历史通过记录，只影响产品化后的命名与入口边界

完整产品化蓝图与验收标准见 [../design/productization_program.md](../design/productization_program.md)。

### 阶段目标

证明系统已经具备一个强大、完整、可发现的统一命令行入口：

- 统一开发/验收 CLI 的 help 可以完整呈现
- 现有 primitive / access / offline / governance / gate / report 都能通过统一 CLI 触达
- 用户和开发者可以仅通过该入口体验和测试现有记忆模块能力
- 后端、profile、输出格式和 demo 场景都有统一命令语义

阶段 J 明确**不要求**：

- 前端图形界面
- 真实 LLM provider 适配层
- 开发态内部结构可视化

### MUST-PASS 指标

| Gate ID | 指标 | 阈值 | 验证方式 |
| --- | --- | --- | --- |
| `J-1` | CLI help 完整度 | `mind -h` 与全部一级命令 help coverage `= 100%` | CLI help audit |
| `J-2` | 命令族覆盖 | `primitive / access / offline / governance / gate / report / demo / config = 8/8` 全部可达 | CLI smoke |
| `J-3` | 体验流覆盖 | 在 `MindCliScenarioSet v1` 上，`ingest-read / retrieve / access-run / offline-job / gate-report = 5/5` 主流程通过 | scenario tests |
| `J-4` | profile / backend 切换正确性 | `SQLite / PostgreSQL` profile 切换、配置优先级与参数解析样例 `20/20` 通过 | CLI config audit |
| `J-5` | 输出与退出码稳定性 | `text / json` 输出 schema 校验通过率 `= 100%`；非法输入的非零退出码覆盖率 `= 100%` | contract tests |
| `J-6` | 旧能力包装无回归 | 现有阶段 gate 与关键能力通过统一 CLI 包装后成功率 `= 100%` | regression run |

### 通过结论

当 `J-1 ~ J-6` 全部通过时，阶段 J `PASS`。
此时系统才真正具备一个可体验、可测试、可演示的统一命令行入口；阶段 K 才适合继续把能力层抽象成可切换模型接口。

---

## 阶段 K Gate：LLM Capability Layer 完成

### 阶段目标

证明现有能力已经被收敛为统一调用层，并且可以平滑切换不同模型能力支持：

- `summarize / reflect / answer / offline_reconstruct` 具备统一 capability 接口
- 模型调用可以通过配置切换
- 兼容主流 `openai / claude / gemini` 风格接口
- 不配置外部模型时，现有 deterministic baseline 仍能继续工作

阶段 K 明确**不要求**：

- 前端可视化入口
- 把全部能力强制绑定到外部模型
- provider 私有特性主导系统主语义

### MUST-PASS 指标

| Gate ID | 指标 | 阈值 | 验证方式 |
| --- | --- | --- | --- |
| `K-1` | capability 合约完整度 | `summarize / reflect / answer / offline_reconstruct = 4/4` 全部使用统一请求 / 响应 contract | contract audit |
| `K-2` | provider 兼容覆盖 | `openai / claude / gemini = 3/3` 兼容接口样例全部通过 | adapter bench |
| `K-3` | 模型切换透明性 | 同一 capability 调用方在不改业务调用代码的前提下切换 provider / model 成功率 `= 100%` | integration tests |
| `K-4` | fallback / 失败收敛 | provider 不可用样例中，`fallback_success + structured_failure = 100%`；silent drift `= 0` | failure audit |
| `K-5` | 现有本地能力无回归 | 不配置外部模型时，既有本地 gate 与 deterministic baseline 成功率 `= 100%` | regression run |
| `K-6` | 模型调用 trace 完整率 | 外部 capability 调用的 `provider / model / endpoint / version / timing` 记录覆盖率 `= 100%` | trace audit |
| `K-7` | 适配器场景通过率 | `CapabilityAdapterBench v1` 上总体场景通过率 `>= 0.95` | adapter benchmark |

### 通过结论

当 `K-1 ~ K-7` 全部通过时，阶段 K `PASS`。
此时模型能力层不再是零散调用点，而成为可配置、可切换、可回退的统一能力面；阶段 L 才适合深入内部做完备观测。

当前本地验证入口：

- `mindtest gate phase-k`
- `mindtest report phase-k-compatibility`
- `mindtest-phase-k-gate`
- `mindtest-phase-k-compatibility-report`

---

## 阶段 L Gate：Development Telemetry 完成

### 阶段目标

证明系统已经能在不改变现有功能语义的前提下，完备采集内部结构、状态变化和关键决策过程：

- 开发模式下能收集足够完整的内部执行数据
- 采集结果能够还原对象变化、上下文选择和离线动作链
- telemetry 机制有显式开关，不污染普通模式

阶段 L 明确**不要求**：

- 性能优化
- 正式生产态 telemetry 成本控制
- 面向终端用户的图形化展示

### MUST-PASS 指标

| Gate ID | 指标 | 阈值 | 验证方式 |
| --- | --- | --- | --- |
| `L-1` | 观测面覆盖 | `primitive / retrieval / workspace / access / offline / governance / object_delta = 7/7` 全部接入 | instrumentation audit |
| `L-2` | 状态变化完整率 | 在 `InternalTelemetryBench v1` 上，before / after / delta 采集覆盖率 `>= 0.95` | state-delta audit |
| `L-3` | 因果关联完整率 | `run_id / operation_id / job_id / workspace_id / object_version` 关联链覆盖率 `= 100%` | trace audit |
| `L-4` | 开关隔离 | 开发模式关闭时持久 telemetry 记录数 `= 0`，功能结果无行为漂移 | toggle regression |
| `L-5` | 可回放时间线完整率 | 在 `InternalTelemetryBench v1` 上，可重建有序内部执行时间线的样例比例 `>= 0.95` | replay audit |
| `L-6` | debug 数据完备度 | mode switch、candidate 排序、workspace 选择、budget、governance selection 等关键内部字段覆盖率 `>= 0.95` | debug-field audit |

### 通过结论

当 `L-1 ~ L-6` 全部通过时，阶段 L `PASS`。
此时系统已经为后续内部操作可视化准备好数据底座；阶段 M 才有必要把这些能力转成前端入口。

---

## 阶段 M Gate：Frontend Experience 完成

### 阶段目标

证明系统已经具备面向体验的前端入口：

- 有统一功能体验入口
- 有后端 / 模型 / 开发模式配置入口
- 有内部操作可视化和 debug 入口
- 前端不会破坏现有 CLI 与后端语义

阶段 M 明确**不要求**：

- 原生移动端应用
- 完整产品级运营后台
- 提前实现治理重塑或人格层新能力

### MUST-PASS 指标

| Gate ID | 指标 | 阈值 | 验证方式 |
| --- | --- | --- | --- |
| `M-1` | 功能体验流覆盖 | 在 `FrontendExperienceBench v1` 上，`ingest / retrieve / access / offline / gate-demo = 5/5` 主流程通过 | frontend E2E |
| `M-2` | 配置入口完整度 | backend / profile / provider / model / dev-mode 配置项覆盖率 `= 100%` | config audit |
| `M-3` | debug 可视化完备度 | 内部事件时间线、对象变化、context 选择和 evidence 支撑可视化覆盖率 `>= 0.95` | debug UI audit |
| `M-4` | 前后端 contract 稳定性 | 前后端 JSON contract 校验通过率 `= 100%` | API contract tests |
| `M-5` | 多端可用性 | 关键页面在 desktop / mobile viewport 的渲染与基本交互通过率 `= 100%` | responsive audit |
| `M-6` | debug 隔离 | debug 入口仅在开发模式下可用；普通体验流无额外泄露与权限漂移 | dev-mode regression |

### 通过结论

当 `M-1 ~ M-6` 全部通过时，阶段 M `PASS`。
此时系统已经具备完整的体验入口、配置入口和可视化 debug 入口；原本更重的治理执行与人格层工作顺延到后续阶段。

当前本地验证入口：

- `mindtest gate phase-m`
- `mindtest-phase-m-gate`

---

## 阶段 N Gate：Governance / Reshape 完成

### 阶段目标

证明系统已经具备重治理、重塑和清理能力：

- `plan / preview / approve / execute` 治理链可以稳定执行
- mixed-source 派生对象可以按 `support unit` 正确重写
- `erase_scope` 可以按声明范围完成清理
- 治理执行不会在普通路径、日志、缓存或工件里留下泄露

阶段 N 明确**不要求**：

- persona / projection 实现
- 完整产品级合规工作流、工单系统或多租户策略编排
- 任何绕开 provenance / governance audit 的“快捷删除”

### MUST-PASS 指标

| Gate ID | 指标 | 阈值 | 验证方式 |
| --- | --- | --- | --- |
| `N-1` | raw-object preview 正确率 | 在 `ProvenanceGovernanceBench v1` 上，受影响原始对象 preview 的 `precision >= 0.95` 且 `recall >= 0.95` | governance fixture audit |
| `N-2` | support-unit preview 正确率 | 在 `ProvenanceGovernanceBench v1` 上，受影响 `support unit` preview 的 `precision >= 0.95` 且 `recall >= 0.95` | governance fixture audit |
| `N-3` | mixed-source rewrite 判定正确率 | `retained / rewritten / dropped` 判定准确率 `>= 0.95` | rewrite audit |
| `N-4` | 重写后结构完整性 | 重写后对象 dangling support refs `= 0`；new-version lineage 完整率 `= 100%`；受影响对象的 provenance footprint 更新率 `= 100%` | structural integrity audit |
| `N-5` | 默认 `erase_scope` 清理完成率 | `memory_world_plus_artifacts` scope 内的清理完成率 `= 100%` | scope cleanup audit |
| `N-6` | `full` scope 审批与清理完整率 | `erase(full)` 样例全部存在 `approve`；声明 `full` scope 内的清理完成率 `= 100%` | full-scope audit |
| `N-7` | 治理后泄露率 | 被 `conceal` 或 `erase` 的内容经 `read / retrieve / workspace / index / cache / report / log` 旁路泄露的比例 `= 0` | leak regression |
| `N-8` | 治理执行恢复与幂等性 | `plan / preview / approve / execute / artifact_cleanup` 审计链覆盖率 `= 100%`；中断恢复 / 重试 / 幂等回归全部通过 | fault-injection audit |

### 通过结论

当 `N-1 ~ N-8` 全部通过时，阶段 N `PASS`。
此时系统才真正具备“按来源主动重塑记忆网络”的工程能力，而不是只有 provenance 标注和基础隔离。

---

## 阶段 O Gate：Persona / Projection 完成

### 阶段目标

证明“组织好的记忆可以长成人格层”已经从研究问题推进为可约束的工程能力：

- persona projection 能稳定利用自传性、偏好和价值相关记忆
- 人格表达是有证据支撑、可治理、可更新的
- persona layer 不会变成绕开记忆系统的新真相源
- 引入人格投影后，不会明显破坏非人格任务的完成质量

阶段 O 明确**不要求**：

- 完整情绪模拟系统
- 独立、权威、不可追溯的 `PersonaObject`
- 通过参数更新而不是记忆对象来固化人格

### MUST-PASS 指标

| Gate ID | 指标 | 阈值 | 验证方式 |
| --- | --- | --- | --- |
| `O-1` | autobiographical grounding | 在 `PersonaProjectionBench v1` 上，自传性 persona 输出中可追溯到 autobiographical supports 或 prompt 已知信息的比例 `>= 0.95` | evidence audit |
| `O-2` | preference / value grounding | 偏好与价值相关 persona 输出中可追溯到 preference / value supports 的比例 `>= 0.95` | evidence audit |
| `O-3` | persona 一致性 | 同一 identity bundle 内的自我表述、偏好表达和价值判断一致性 `>= 0.90`，同时 `ConstraintSatisfaction >= 0.95` | projection benchmark |
| `O-4` | 治理后的 persona 适配 | 对 persona 相关记忆执行治理后，陈旧 persona 表达泄露率 `= 0`；更新后投影命中率 `>= 0.95` | governance-coupled regression |
| `O-5` | unsupported persona 幻觉率 | 无记忆 / prompt 支撑的自传性或价值性断言比例 `<= 0.05` | unsupported-claim audit |
| `O-6` | 非 persona 任务回归控制 | 在 `EpisodeAnswerBench v1` 的中性任务子集上，启用 persona projection 后 `AQS` 平均降幅 `<= 0.02`，`ConstraintSatisfaction` 平均降幅 `<= 0.01` | A/B regression |

### 通过结论

当 `O-1 ~ O-6` 全部通过时，阶段 O `PASS`。
此时人格层可以被视为建立在记忆世界之上的可投影能力，而不是额外造出的一个黑箱人格模块。

---

## 7. 实施建议

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
