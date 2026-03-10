# MIND SPEC v0.3

## 0. 文档目的

这份文档以 MIND 的阶段 A 正式规范为基线，并纳入 Phase G 之后冻结的 addendum。

它的职责不是解释愿景，而是冻结后续实现必须遵守的语义边界。

文档约定：

- 未显式标注 `Post-Phase-G Addendum` 的段落，对应阶段 A 基线
- 显式标注 `Post-Phase-G Addendum` 的段落，只约束后续阶段，不追溯推翻 A ~ G 的既有通过记录

阶段 A 基线完成后，阶段 B / C / D 的开发都应该以本文的基线部分为准；后续阶段则继续受 addendum 约束，而不是在实现过程中临时重新定义：

基线部分：
- 什么是 memory world
- 什么是 memory object
- 什么是 primitive
- 什么是 workspace view
- 什么是 memory utility objective
- 什么属于 online loop
- 什么属于 offline loop

addendum 部分：
- 什么是 runtime memory access policy
- 什么是 provenance control plane
- 什么属于 governance / reshape loop

本文的阶段 A 基线部分对应 [phase_gates.md](./phase_gates.md) 中的阶段 A gate；addendum 部分对应其中的 post-G 扩展约束。

---

## 0.1 规范范围

本文以阶段 A 基线为主，并记录 Phase G 之后补入的 addendum；它不定义：

- 存储实现细节
- 向量索引实现细节
- 具体模型选型
- benchmark 数据集内容
- 策略学习算法

本文定义的是“系统语义”，不是“代码实现”。

---

## 0.2 术语

| 术语 | 定义 |
| --- | --- |
| `memory world` | MIND 管理的外部可编辑记忆环境 |
| `memory object` | 记忆世界中的基本对象单位 |
| `primitive` | Agent 可对记忆世界执行的最小操作 |
| `workspace view` | 当前任务的有限工作记忆索引视图 |
| `runtime access mode` | 运行时为任务选择的记忆访问深度档位 |
| `episode` | 一次完整任务过程的结构化记录 |
| `promotion` | 将更局部、更临时的经验提升为更稳定对象 |
| `reconsolidation` | 被取回并修订的对象生成新版本的过程 |
| `provenance` | 与原始来源主体绑定的控制面来源记录，不等同于对象 lineage |
| `provenance footprint` | 派生或聚合对象基于底层 provenance 汇总出的治理摘要 |
| `support unit` | 对象内部最小可治理、可重写、可审计的支撑单元 |
| `governance / reshape loop` | 独立于 online / offline 的高权限主动治理流程 |
| `conceal` | 逻辑不可见、可恢复的治理性遗忘 |
| `erase` | 物理擦除或带 tombstone 的不可恢复治理性删除 |

---

## 1. Memory World

## 1.1 定义

`memory world` 是一个外部、可编辑、可追溯、可评估的状态空间。

MIND 的 Agent 不直接修改自身参数，而是通过 primitive 对 `memory world` 进行操作，从而改变未来任务中的记忆可用性。

## 1.2 Post-Phase-G Addendum: 扩展后的最小状态结构

在不回滚阶段 A data plane 定义的前提下，Post-Phase-G addendum 将 `memory world` 扩展为 data plane 与 control plane 的组合：

### data plane

| 状态成分 | 含义 |
| --- | --- |
| `objects` | 当前存在的全部 memory objects |
| `relations` | 对象之间的结构关系 |
| `versions` | 对象版本链与对象 lineage |
| `priority_state` | 对象优先级、可见性、保留状态 |
| `budget_state` | 当前任务或维护周期的成本约束状态 |

### control plane

| 状态成分 | 含义 |
| --- | --- |
| `provenance_ledger` | 原始来源主体、来源环境、采集时间与保留策略 |
| `governance_audit` | `conceal / erase / reshape` 的计划、预览、审批与执行记录 |

形式化记作：

`M = (D, C)`

其中：

- `D = (O, R, V, P, B)`
- `C = (Q, G)`
- `O` = objects
- `R` = relations
- `V` = versions / lineage
- `P` = priority state
- `B` = budget state
- `Q` = provenance ledger
- `G` = governance audit

补充约束：

- `control plane` 支持治理、审计和主动重塑，但不直接参与运行时记忆优化
- provenance 可以被查看、筛选和治理，但不进入 online / offline 的 ranking 或 weighting

## 1.3 Post-Phase-G Addendum: `source_refs` 与 `provenance` 的区分

Post-Phase-G addendum 明确区分两类“可追溯性”：

- `source_refs`：memory world 内部的对象 lineage，回答“这个对象从哪些对象派生而来”
- `provenance`：控制面来源记录，回答“这条原始数据来自谁、何时、什么环境”

冻结规则：

- `source_refs` 属于对象 schema 的一部分，是记忆演化语义
- `provenance` 属于 control plane，不进入对象统一 `10` 个必填字段
- `RawRecord` 与外部导入的原始对象应绑定 authoritative direct provenance
- `TaskEpisode` 与其他派生对象默认不持有新的 authoritative direct provenance，只允许持有 `provenance footprint`
- `provenance footprint` 只服务治理 preview、审计和说明，不得作为 runtime 优化信号

### direct provenance 最小字段集

该 addendum 对 direct provenance 冻结以下最小必填字段：

| 字段 | 含义 |
| --- | --- |
| `provenance_id` | provenance 记录稳定 ID |
| `bound_object_id` | 直接绑定的原始对象 ID |
| `bound_object_type` | `RawRecord | ImportedRawRecord` |
| `producer_kind` | `user | model | tool | system | operator | dataset` |
| `producer_id` | 来源主体稳定 ID |
| `captured_at` | 原始事件发生时间 |
| `ingested_at` | 写入 MIND 的时间 |
| `source_channel` | `chat | api | batch_import | tool_runtime | system_internal` |
| `tenant_id` | 租户或命名空间 |
| `retention_class` | `default | sensitive | ephemeral | regulated` |

该 addendum 允许以下治理筛选字段按场景选填：

- `user_id`
- `model_id`
- `model_provider`
- `model_version`
- `ip_addr`
- `device_id`
- `machine_fingerprint`
- `session_id`
- `request_id`
- `conversation_id`
- `episode_id`

补充约束：

- `ip_addr / device_id / machine_fingerprint` 允许以明文进入 provenance，但必须视为高敏控制面字段
- 这些高敏字段默认不出现在普通运行时日志、评测输出和低权限报表中
- provenance 过滤条件必须落在 control plane，而不是通过普通 memory object `metadata` 旁路实现

## 1.4 边界

MIND 在阶段 A 基线中明确管理：

- 记忆对象
- 关系结构
- 版本与追溯
- priority / visibility / archive 状态
- 在线和离线记忆操作

Post-Phase-G addendum 继续补入：

- provenance control plane
- governance / reshape 操作

MIND 在阶段 A 不管理：

- LLM 权重更新
- 工具本身的外部副作用
- 业务系统权限模型
- 用户产品层 UI

## 1.5 设计约束

- 所有派生对象都必须可追溯到源对象
- 所有更新都必须可版本化，不允许 silent overwrite
- 所有对象都必须能参与 priority 调整
- provenance 不得被偷偷并入普通检索特征或摘要内容生成特征
- 所有治理动作都必须可审计，且不得绕过权限与范围约束
- Post-Phase-G addendum 中的 online / offline / governance 扩展都必须落到 world state 或 governance audit 变化上

---

## 2. Object Schema

## 2.1 设计原则

阶段 A 的对象模型应满足：

- 类型数尽量少，但足够支撑后续演化
- 所有对象统一遵守同一组核心字段
- 对象可被 primitive 统一读写
- 对象能支撑从 episodic 到 semantic / procedural 的迁移

## 2.2 核心对象类型

阶段 A 冻结 8 类核心对象：

| 对象类型 | 作用 |
| --- | --- |
| `RawRecord` | 保留最原始的事件、消息、工具调用或工具结果 |
| `TaskEpisode` | 一次完整任务过程的聚合对象 |
| `SummaryNote` | 局部压缩后的摘要对象 |
| `ReflectionNote` | 任务后反思对象 |
| `EntityNode` | 可被多处引用的实体节点 |
| `LinkEdge` | 对象之间的显式关系边 |
| `WorkspaceView` | 当前任务的有限工作记忆视图 |
| `SchemaNote` | 跨 episode 稳定共性或规则的中间表示 |

说明：

- `ProcedureNote` 暂不作为阶段 A 强制对象
- 但 `SchemaNote` 的 `metadata.kind` 可以取值 `semantic` 或 `procedural`
- 如果后续阶段证明程序性经验独立性足够强，再拆出 `ProcedureNote`

## 2.3 所有对象的统一必填字段

阶段 A 规定，所有对象都必须包含以下 `10` 个必填字段：

| 字段 | 类型 | 含义 |
| --- | --- | --- |
| `id` | `string` | 全局唯一对象 ID |
| `type` | `enum` | 对象类型 |
| `content` | `object|string` | 对象主体内容 |
| `source_refs` | `string[]` | 源对象引用 |
| `created_at` | `datetime` | 创建时间 |
| `updated_at` | `datetime` | 最近更新时间 |
| `version` | `integer` | 版本号，从 `1` 开始 |
| `status` | `enum` | `active / archived / deprecated / invalid` |
| `priority` | `float` | `[0,1]` 区间内的优先级 |
| `metadata` | `object` | 类型特定附加信息 |

## 2.4 通用字段约束

- `id` 必须稳定，不因版本更新而改变对象身份
- `source_refs` 对于派生对象不能为空
- `version` 每次 reconsolidation 或对象修订必须递增
- `priority` 不允许缺失
- `status` 不允许省略

## 2.5 各对象的类型特定字段

### `RawRecord`

`metadata` 必须包含：

- `record_kind`: `user_message | assistant_message | tool_call | tool_result | system_event`
- `episode_id`
- `timestamp_order`

补充约束：

- `RawRecord` 的 authoritative direct provenance 记录在 control plane 中，而不是对象 `metadata` 中

### `TaskEpisode`

`metadata` 必须包含：

- `task_id`
- `goal`
- `result`
- `success`
- `record_refs`

补充约束：

- `TaskEpisode` 的来源语义默认由 `record_refs` 继承，不单列新的 authoritative direct provenance

### `SummaryNote`

`metadata` 必须包含：

- `summary_scope`
- `input_refs`
- `compression_ratio_estimate`

### `ReflectionNote`

`metadata` 必须包含：

- `episode_id`
- `reflection_kind`: `success | failure | mixed`
- `claims`

### `EntityNode`

`metadata` 必须包含：

- `entity_name`
- `entity_kind`
- `alias`

### `LinkEdge`

`content` 采用结构化对象，必须包含：

- `src_id`
- `dst_id`
- `relation_type`

`metadata` 必须包含：

- `confidence`
- `evidence_refs`

### `WorkspaceView`

`metadata` 必须包含：

- `task_id`
- `slot_limit`
- `slots`
- `selection_policy`

### `SchemaNote`

`metadata` 必须包含：

- `kind`: `semantic | procedural`
- `evidence_refs`
- `stability_score`
- `promotion_source_refs`

## 2.6 类型判定原则

阶段 A 对对象类型采用以下冻结原则：

- 一个对象类型只承载一个主要语义职责
- 一个对象只能有一个主类型，不允许同时声明为多种对象
- 类型判定优先依据对象的语义职责，而不是生成它的模型、存储位置或实现细节
- 证据、解释、结构、执行上下文这四类职责不应混在同一个对象里
- 当同一份内容可能以多种形式表达时，应选择“语义更专门、约束更强”的类型

形式化地，阶段 A 推荐把 8 类对象理解为 4 层：

- 证据层：`RawRecord`、`TaskEpisode`
- 解释层：`SummaryNote`、`ReflectionNote`
- 结构层：`EntityNode`、`LinkEdge`、`SchemaNote`
- 执行层：`WorkspaceView`

## 2.7 对象类型判定规则

以下规则用于回答“一个新对象应当属于哪一类”。

### `RawRecord` 判定规则

对象当且仅当满足以下条件时应判定为 `RawRecord`：

- 它表达的是一次直接观察到的原始事件，而不是对多个对象的再加工
- 它对应明确的消息、工具调用、工具结果或系统事件
- 它可以被放入某个 `episode` 的时间顺序中
- 它不声称任务级结论、经验总结或跨 episode 规律

不应判定为 `RawRecord` 的情况：

- 对多条记录做压缩后的内容
- 对任务成败的诊断
- 对实体或关系的抽取结果

### `TaskEpisode` 判定规则

对象当且仅当满足以下条件时应判定为 `TaskEpisode`：

- 它表达的是一次完整任务过程的边界化聚合
- 它的主要作用是把同一任务下的多个 `RawRecord` 组织为可回放、可评估单元
- 它必须显式包含任务目标、任务结果、成功与否以及 `record_refs`
- 它不表达跨 episode 的一般规律

不应判定为 `TaskEpisode` 的情况：

- 仅记录单条原始事件
- 仅对局部材料做摘要
- 仅表达单个实体或显式关系

### `SummaryNote` 判定规则

对象当且仅当满足以下条件时应判定为 `SummaryNote`：

- 它来自一个或多个已有对象的压缩、整理或重述
- 它的主要目标是降低后续读取和 workspace 构建成本
- 它表达的是“有哪些关键信息”，而不是“为什么成败”或“通常应如何做”
- 它的适用范围默认局限于当前输入证据，不自动提升为跨 episode 规则

不应判定为 `SummaryNote` 的情况：

- 以成败归因为主的对象
- 以跨任务稳定模式为主的对象
- task-scoped 的 slot 集合

### `ReflectionNote` 判定规则

对象当且仅当满足以下条件时应判定为 `ReflectionNote`：

- 它面向单个 `TaskEpisode`
- 它显式包含成功、失败或混合结果的评价
- 它的核心内容是原因分析、经验得失、改进建议或风险提示
- 它仍然受限于单个 episode 的证据边界，不直接声称“这已经是一般规律”

不应判定为 `ReflectionNote` 的情况：

- 只做信息压缩、不做评价
- 已经抽象为跨 episode 稳定规则
- 只是当前任务的工作记忆视图

### `EntityNode` 判定规则

对象当且仅当满足以下条件时应判定为 `EntityNode`：

- 它的主要职责是为可重复引用的实体提供稳定身份
- 它可以被多个 episode、摘要或关系边复用
- 它关注“这是什么 / 叫什么 / 属于哪类”，而不是讲述一次具体事件
- 它不直接表达两个对象之间的关系结论

不应判定为 `EntityNode` 的情况：

- 某次交互中出现的单次事实陈述
- 带方向的关系断言
- 对多个实体共性做出的抽象规律

### `LinkEdge` 判定规则

对象当且仅当满足以下条件时应判定为 `LinkEdge`：

- 它表达的是两个对象之间的显式、带类型、可审计关系
- 它必须有 `src_id`、`dst_id`、`relation_type`
- 它必须附带 `evidence_refs`
- 它的主要职责是把“关系本身”作为一等对象暴露给 primitive 和检索层

不应判定为 `LinkEdge` 的情况：

- 仅作为 `source_refs` 保存溯源信息
- 只记录某个对象自己的属性
- 当前任务的 slot 选择结果

### `WorkspaceView` 判定规则

对象当且仅当满足以下条件时应判定为 `WorkspaceView`：

- 它是当前任务的有限工作记忆句柄集合
- 它显式受 `task_id` 和 `slot_limit` 约束
- 它的核心内容是 `slots` 以及各 slot 的证据、理由、展开入口
- 它服务的是当前任务的即时求解，而不是长期知识沉淀

不应判定为 `WorkspaceView` 的情况：

- 可长期复用的摘要或规则对象
- 对象之间的稳定图结构
- 原始事件日志

### `SchemaNote` 判定规则

对象当且仅当满足以下条件时应判定为 `SchemaNote`：

- 它表达的是跨 episode 可复用的稳定模式、规则或流程结构
- 它必须有跨 episode 证据支持，而不是只依赖单个任务
- 它必须显式说明 `kind`、`evidence_refs`、`stability_score`
- 它的主要用途是为未来任务提供长期复用的 semantic / procedural 结构

不应判定为 `SchemaNote` 的情况：

- 仍停留在单个 episode 的诊断
- 只是局部压缩后的摘要
- 未经过证据支持的泛化结论

## 2.8 判定优先级与冲突消解

当一个候选对象看起来同时接近多个类型时，按以下规则处理：

1. 先判断它是不是直接观测到的原始事件；如果是，则固定为 `RawRecord`
2. 否则判断它是不是一次完整任务的聚合边界；如果是，则固定为 `TaskEpisode`
3. 否则判断它是不是 task-scoped、slot-limited 的工作视图；如果是，则固定为 `WorkspaceView`
4. 否则判断它是不是稳定实体身份；如果是，则固定为 `EntityNode`
5. 否则判断它是不是显式关系对象；如果是，则固定为 `LinkEdge`
6. 否则判断它是不是跨 episode 的稳定规律；如果是，则固定为 `SchemaNote`
7. 否则判断它是不是单 episode 的评价与诊断；如果是，则固定为 `ReflectionNote`
8. 其余由已有对象压缩、整理而来的派生内容，归入 `SummaryNote`

补充约束：

- `SummaryNote` 不能偷偷承载 `ReflectionNote` 的评价职责
- `ReflectionNote` 不能直接充当 `SchemaNote`
- `WorkspaceView` 不能兼作长期知识对象
- `LinkEdge` 不能被 `source_refs` 或 `metadata` 中的隐式字段替代

## 2.9 对象状态机

所有对象的合法状态流转为：

```text
active -> archived
active -> deprecated
active -> invalid
archived -> active
deprecated -> active
```

约束：

- `invalid` 只能由校验失败、冲突确认或人工审计触发
- `archived` 表示弱可见，不等于删除
- 阶段 A 不允许物理删除作为常规操作

## 2.10 Post-Phase-G Addendum: Provenance 绑定规则

Post-Phase-G addendum 对 provenance 绑定方式冻结如下：

- direct provenance 默认只绑定到 `RawRecord` 或外部导入的原始对象
- `TaskEpisode`、`SummaryNote`、`ReflectionNote`、`SchemaNote`、`WorkspaceView`、`EntityNode`、`LinkEdge` 都属于派生或聚合对象
- 派生或聚合对象应通过 `source_refs + provenance ledger` 回溯到底层 direct provenance
- 如需加速治理 preview，可为派生对象维护 `provenance footprint`
- `provenance footprint` 不是新的事实来源，不得替代 direct provenance

## 2.11 Post-Phase-G Addendum: Support Unit 与可重写性

`support unit` 是治理系统中的最小作用单元。

它不是 memory object，也不是新的核心对象类型，而是对“对象内部哪些部分可以被保留、重写或删除”的冻结语义。

Post-Phase-G addendum 对 `support unit` 冻结以下最小控制字段：

| 字段 | 含义 |
| --- | --- |
| `unit_id` | 对象内稳定单元 ID |
| `unit_kind` | 单元类型，例如 `claim / slot / facet / edge` |
| `payload` | 当前单元表达的内容或结构 |
| `evidence_refs` | 直接支撑该单元的对象引用 |
| `direct_provenance_ids` | 该单元直接依赖的 provenance 记录 |
| `support_rule` | 单元有效性的判定规则 |
| `rewrite_policy` | `none | deterministic | model_assisted` |
| `status` | `active | retained | rewritten | dropped` |

该 addendum 冻结的 `support_rule v1`：

- `min_support_count >= 1`

也就是：

- 剩余有效 `evidence_refs = 0` 时，该单元必须 `dropped`
- 剩余有效 `evidence_refs >= 1` 且 payload 无需变化时，该单元可以 `retained`
- 剩余有效 `evidence_refs >= 1` 但 payload 已受影响时，该单元必须 `rewritten`

各对象的最小治理粒度冻结如下：

| 对象类型 | 最小治理粒度 | 说明 |
| --- | --- | --- |
| `RawRecord` | 整条记录 | 不允许局部重写 |
| `TaskEpisode` | 整个 episode 聚合 | 基于剩余 `record_refs` 整体重建新版本 |
| `SummaryNote` | `claim` | 治理能力要求 claim 级保留 / 重写 / 删除 |
| `ReflectionNote` | `claim` | 与 `SummaryNote` 一样按 claim 管理 |
| `EntityNode` | `facet` | 例如 `name / alias / description / attribute` |
| `LinkEdge` | 整条 `edge` | 只允许整条保留或删除 |
| `WorkspaceView` | `slot` | slot 变化后整体重渲染新对象版本 |
| `SchemaNote` | `rule / claim` | 跨 episode 规则需可局部重写 |

补充约束：

- `support unit` 是治理扩展 contract，不属于当前统一 `10` 个对象必填字段
- 但任何宣称支持 governance / reshape 的实现，都必须能物化或可确定性导出上述单元映射
- mixed-source 派生对象的治理结果不允许只“删掉一个依赖”却保持错误 payload 不变
- mixed-source 派生对象也不要求一律整对象失效；首选策略是按最小治理粒度重写

### 2.11.1 Governance Projection Contract

由于 `support unit` 不进入统一 `10` 个对象必填字段，任何声称支持 governance / reshape 的实现，都必须为下列对象提供确定性的治理投影。

这个投影可以落在对象的结构化字段中，也可以落在 control plane sidecar 中，但必须稳定、可审计、可重放。

| 对象类型 | 最小治理投影要求 |
| --- | --- |
| `SummaryNote` | 必须能导出有序 `claim` 列表；每个 claim 至少有 `unit_id / payload / evidence_refs` |
| `ReflectionNote` | 必须把 `metadata.claims` 或等价结构稳定映射为 claim 级单元 |
| `EntityNode` | 必须能导出 `facet` 级单元，至少覆盖 `entity_name`、每个 `alias` 及已持久化属性 |
| `LinkEdge` | 必须能导出单一 `edge` 单元，绑定 `src_id / dst_id / relation_type / evidence_refs` |
| `WorkspaceView` | 必须把每个 `metadata.slots` 项映射为 `slot` 单元，并保留其证据与展开入口 |
| `SchemaNote` | 必须能导出有序 `rule` 或 `claim` 列表；纯不可分 prose 不足以支撑细粒度治理 |

补充约束：

- `governance_projection` 是治理能力 contract，不等同于新增核心对象字段
- 纯文本对象若无法稳定导出 `claim / rule / facet / slot` 单元，就不能宣称支持对应粒度的重写
- 若某实现暂时只支持 `retain / drop`，必须显式声明该对象类型尚不支持细粒度 rewrite，而不是默认 claim 级可改

---

## 3. Primitive Catalog

## 3.1 设计原则

阶段 A 的 primitive 应满足：

- 低层
- 可组合
- 可审计
- 可预算约束
- 不偷偷写死高层策略

### 3.1.1 Primitive 的语义边界原则

阶段 A 对 primitive 采用以下冻结原则：

- 一个 primitive 只承载一种主要记忆动作，不同时承担多个无关职责
- primitive 的边界应按“对 memory world 做了什么”来划分，而不是按实现模块或模型提示词来划分
- primitive 可以产生新对象、更新对象状态，或返回可操作句柄，但不应偷偷执行高层策略闭环
- 如果一个操作只是多个 primitive 的固定组合、或只是某个 loop 中的调度步骤，则不应优先提升为独立 primitive
- 如果一个操作只是某个对象类型的特例写入，应先判断能否由现有 primitive + type rule 表达

形式化地，阶段 A 的 7 个 primitive 覆盖 5 类动作：

- 摄取：`write_raw`
- 访问：`read`、`retrieve`
- 派生：`summarize`、`reflect`
- 结构化：`link`
- 维护：`reorganize_simple`

### 3.1.2 Primitive 的必要性与最小性标准

一个 primitive 被视为阶段 A 必需，当且仅当它满足以下至少一条：

- 没有它，某类核心对象无法被稳定生成或访问
- 没有它，online / offline loop 中会出现无法表达的必要动作
- 没有它，系统会被迫把关键语义藏进高层策略或隐式副作用
- 没有它，后续评测与审计无法把某类动作单独量化

一个 primitive 不应被单列，如果它只是：

- 更高层流程的一个固定组合
- 单纯的策略选择、调度、排序或阈值决策
- 某个已有 primitive 的参数化特例
- 只在实现层有差异、但在语义层并未新增动作类别

阶段 A 冻结 `7` 个必需 primitive。

## 3.2 Primitive 一览

| Primitive | 作用 |
| --- | --- |
| `write_raw` | 写入原始记录 |
| `read` | 按明确引用读取对象 |
| `retrieve` | 根据查询和预算检索候选对象 |
| `summarize` | 生成派生摘要对象 |
| `link` | 建立显式关系边 |
| `reflect` | 生成任务后反思对象 |
| `reorganize_simple` | 执行轻量重组、归档或降权 |

### 3.2.1 对 7 个 primitive 的必要性审核

#### `write_raw`

必要性：

- 它是所有派生对象的证据根入口
- 没有它，`RawRecord` 只能通过隐式日志或外部系统进入 world state，trace 会断裂
- 它把“写入原始经验”从“生成派生表示”中严格分离，有利于后续评估污染率与压缩收益

#### `read`

必要性：

- `read` 负责按明确引用获取对象，语义上是确定性访问
- 它不能被 `retrieve` 替代，因为 `retrieve` 是带查询、排序和预算的候选召回
- 将精确访问与模糊检索分开，能让算法分别优化 object fetch 和 candidate ranking

#### `retrieve`

必要性：

- 没有 `retrieve`，系统只能依赖显式 ID 读取，无法进行开放式记忆召回
- 它为 `keyword / vector / time-window` 等检索后端保留统一语义接口
- 它让“找什么”成为可单独评测和优化的动作，而不是把检索逻辑藏进 `read` 或 prompt

#### `summarize`

必要性：

- 没有 `summarize`，系统只能在原始对象和 workspace 间来回搬运高成本材料
- 它是 `SummaryNote` 的唯一低层生成入口，支撑压缩、复用和长期维护
- 把摘要显式化为 primitive，有利于后续单独优化压缩率、事实保真度和复用率

#### `link`

必要性：

- 没有 `link`，显式关系只能退化为 `metadata` 或 `source_refs` 里的隐式字段
- 它让关系对象成为一等公民，便于后续图检索、证据审计和关系修订
- 它把“建立关系”从“写内容”中剥离出来，避免把结构知识埋在文本里

#### `reflect`

必要性：

- `reflect` 负责生成 episode-level 的评价与诊断，语义上不同于 `summarize`
- 没有它，失败原因、改进建议和经验得失会被塞进 `SummaryNote`，对象边界会变脏
- 将反思显式化，有利于后续单独优化 failure analysis、counterfactual quality 和 promotion precision

#### `reorganize_simple`

必要性：

- 没有它，系统只能不断新增对象，却无法执行 archive / deprecate / reprioritize / schema synthesis
- 它为 offline maintenance 提供最小但完整的世界状态改写入口
- 它是阶段 A 中唯一允许做轻量维护与重组的 primitive，因此必须存在

边界说明：

- `reorganize_simple` 是阶段 A 中最“不纯”的 primitive，因为它聚合了多种维护子动作
- 之所以暂时保留，是为了避免过早把 maintenance primitive 拆得过细，导致策略空间和接口面同时爆炸
- 当后续实验表明 `archive / reprioritize / synthesize_schema` 需要不同优化器或评测时，它应当是第一优先级的拆分对象

### 3.2.2 阶段 A 暂不单列为 primitive 的操作

以下操作在阶段 A 不应优先升级为独立 primitive：

- `build_workspace`：它是 `retrieve + read` 之后的 task-local 视图构造步骤，属于 online loop 组件，不是通用 memory world 改写动作
- `archive / deprecate / reprioritize / synthesize_schema`：它们在阶段 A 先作为 `reorganize_simple` 的参数化子操作存在
- `split / merge`：它们属于对象级 surgery，前期证据不足，过早引入会让 primitive 组合空间失控
- `evaluate`：它属于评测层与 utility 层，不是 memory world 的基础操作
- `replay`：它是 offline loop 的调度步骤，不是最小原子动作
- `promote`：它更接近“准入决策 + 维护执行”的组合，应由 policy 决策加 `reorganize_simple` 落地
- `canonicalize_entity`：它是未来可能出现的 specialized primitive，但阶段 A 尚未证明实体归一是主路径瓶颈
- `governance plan / preview / approve / execute`：它们属于高权限 control-plane workflow，不是 Agent primitive

### 3.2.3 Post-Phase-G Addendum: Governance 为什么不并入 primitive

Post-Phase-G addendum 明确不把 `governance / reshape` 做成 Agent primitive，原因是：

- 它需要高权限与显式审批，不适合暴露给普通 Agent
- 它会跨对象、跨索引、跨工件地做大范围扫描与重写
- 它既包含计划、预览、审批，也包含执行，不是单一世界动作
- 它的正确性依赖 control plane，而不是只依赖 memory object contract

因此：

- `primitive` 继续服务 online / offline 记忆演化
- `governance / reshape` 单列为独立接口与独立执行阶段

## 3.3 Primitive 合约模板

每个 primitive 必须定义：

- `input`
- `output`
- `side_effects`
- `failure_modes`
- `budget_effects`

下面逐一冻结。

### 3.3.1 `write_raw`

**input**

- `record_kind`
- `content`
- `episode_id`
- `timestamp_order`

**output**

- `object_id`
- `version`

**side_effects**

- 新增 `RawRecord`

**failure_modes**

- schema invalid
- missing episode context
- budget exhausted

**budget_effects**

- 增加写入成本
- 增加存储成本

### 3.3.2 `read`

**input**

- `object_ids`

**output**

- `objects`

**side_effects**

- 无对象结构变化
- 可更新访问日志

**failure_modes**

- object not found
- object inaccessible

**budget_effects**

- 增加读取成本

### 3.3.3 `retrieve`

**input**

- `query`
- `query_modes`
- `budget`
- `filters`

**output**

- `candidate_ids`
- `scores`
- `evidence_summary`

**side_effects**

- 无对象结构变化
- 可记录 retrieval trace

**failure_modes**

- unsupported query mode
- budget exhausted
- retrieval backend unavailable

**budget_effects**

- 增加检索成本

### 3.3.4 `summarize`

**input**

- `input_refs`
- `summary_scope`
- `target_kind`

**output**

- `summary_object_id`

**side_effects**

- 新增 `SummaryNote`

**failure_modes**

- empty input refs
- unsupported scope
- summary validation failed

**budget_effects**

- 增加生成成本
- 增加维护成本

### 3.3.5 `link`

**input**

- `src_id`
- `dst_id`
- `relation_type`
- `evidence_refs`

**output**

- `link_object_id`

**side_effects**

- 新增 `LinkEdge`

**failure_modes**

- invalid refs
- self-link not allowed
- evidence missing

**budget_effects**

- 增加写入成本

### 3.3.6 `reflect`

**input**

- `episode_id`
- `focus`

**output**

- `reflection_object_id`

**side_effects**

- 新增 `ReflectionNote`

**failure_modes**

- episode missing
- insufficient evidence
- reflection validation failed

**budget_effects**

- 增加生成成本

### 3.3.7 `reorganize_simple`

**input**

- `target_refs`
- `operation`: `archive | deprecate | reprioritize | synthesize_schema`
- `reason`

**output**

- `updated_ids`
- `new_object_ids`

**side_effects**

- 更新对象状态或优先级
- 可新增 `SchemaNote`

**failure_modes**

- invalid target refs
- unsupported operation
- unsafe state transition

**budget_effects**

- 增加维护成本

## 3.4 Primitive 组合约束

阶段 A 明确允许的典型组合：

- `retrieve -> read -> summarize`
- `retrieve -> read -> reflect`
- `retrieve -> link`
- `reflect -> reorganize_simple`
- `retrieve -> summarize -> reorganize_simple`

阶段 A 明确禁止的行为：

- primitive 直接修改 LLM 权重
- primitive 隐式删除对象
- primitive 生成无 `source_refs` 的派生对象
- primitive 绕过 budget state

---

## 4. Workspace View

## 4.1 定义

`WorkspaceView` 是当前任务的有限工作记忆索引视图。

它不是“尽可能多地塞上下文”，而是“给当前任务保留少量可直接操作的 memory handles”。

## 4.2 基本约束

- `WorkspaceView` 是句柄集合，不是原文集合
- 必须有显式槽位上限 `K`
- 阶段 A 推荐默认 `K = 4`
- `K` 是超参数，不是理论常数

## 4.3 Slot 结构

每个 slot 必须至少包含：

| 字段 | 含义 |
| --- | --- |
| `slot_id` | slot 标识 |
| `summary` | 当前任务可直接消费的简要表示 |
| `evidence_refs` | 支撑当前 slot 的证据对象 |
| `source_refs` | 追溯源对象 |
| `reason_selected` | 为什么被选入 workspace |
| `priority` | 当前 slot 优先级 |
| `expand_pointer` | 展开更多上下文的入口 |

## 4.4 Workspace 构建规则

阶段 A 冻结以下规则：

- workspace 中所有 slot 都必须有 `source_refs`
- workspace 中所有 slot 都必须能回到 `RawRecord` 或 `TaskEpisode`
- workspace 不允许出现无证据 summary
- workspace 构造优先级高于“拼接更多片段”

## 4.5 Workspace 成功标准

在阶段 A，workspace 的 contract 已冻结，但具体质量由阶段 D gate 验证：

- `slot_count <= K`
- 所有 slot 可追溯
- 可以覆盖任务所需关键信息

## 4.6 WorkspaceView 的必要性与最小性审核

`WorkspaceView` 在阶段 A 被视为必要结构，而不是可有可无的实现技巧，理由如下：

- 没有 `WorkspaceView`，系统只能“召回候选对象”，却不能显式表达“当前任务真正持有的有限工作记忆”
- `retrieve` 解决的是“可能相关什么”，`WorkspaceView` 解决的是“当前任务此刻实际操作什么”，二者语义不同
- 没有显式工作视图，online loop 会退化为 `top-k raw / summary` 直接拼接，难以审计、难以对比、也难以优化
- 阶段 D 需要对 slot discipline、gold-fact coverage、token 成本做独立验证，因此必须把工作视图固定为可检查 contract

从最小性角度看，阶段 A 对 `WorkspaceView` 冻结的是接口，而不是构造算法：

- 冻结 slot 上限、traceability 和 slot 字段
- 不冻结具体检索后端、排序器、reranker、slot builder、rendering prompt
- 不假设唯一正确的 workspace strategy，而只要求输出满足统一 contract

因此，`WorkspaceView` 的设计目标不是“提前写死最佳算法”，而是“为后续算法迭代保留稳定操作面”。

## 4.7 Slot 字段的必要性审核

阶段 A 要求的每个 slot 字段都对应一个不可缺语义：

- `slot_id`：让 slot 成为可引用、可比较、可更新的单位；没有它，slot 只能当匿名文本片段处理
- `summary`：提供当前任务可直接消费的低成本表示；没有它，slot 仍需立即展开，失去工作视图意义
- `evidence_refs`：保证 slot 的当前表述有证据支撑；没有它，workspace 会退化成不可审计的临时猜测
- `source_refs`：保证 slot 能回到源对象；没有它，无法满足 traceability contract
- `reason_selected`：显式记录为什么进入 workspace；没有它，后续无法分析 selection policy 的好坏
- `priority`：支持 slot 排序、裁剪、替换；没有它，workspace 无法在预算下做稳定控制
- `expand_pointer`：为按需展开更多上下文保留入口；没有它，系统只能在“全展开”和“完全不展开”之间二选一

这组字段已经接近阶段 A 的最小闭包：再少会损失可追溯性、可审计性或预算控制；再多则容易把 builder 内部实现细节过早冻结为 schema。

## 4.8 WorkspaceView 的边界

以下内容不应直接等同于 `WorkspaceView`：

- 检索候选列表：候选集是召回结果，不是经过任务约束后的有限工作集
- 最终 prompt 全文：prompt 是渲染结果，`WorkspaceView` 是结构化句柄集合
- 长期知识对象：`SummaryNote`、`SchemaNote` 属于长期记忆表示，不属于 task-scoped 工作视图
- 检索 trace 或 builder trace：它们应进入日志 / 调试工件，而不是污染 slot 核心字段

补充约束：

- `WorkspaceView` 应被视为 task-scoped、短生命周期、高可审计对象，而不是长期知识沉淀层
- `WorkspaceView` 可以引用任意对象类型，但不应替代这些对象自身的长期语义职责
- 如果未来需要拆分 workspace builder，优先拆的是 selection / composition / expansion 策略，而不是先增加新的 workspace 对象类型

## 4.9 Post-Phase-G Addendum: Runtime Memory Access Policy

Post-Phase-G addendum 对运行时记忆访问档位冻结如下。

它们不是新的 primitive，也不是新的对象类型，而是 `online loop` 对 retrieval、read、workspace、验证深度的调度策略。

### 4.9.1 四档访问模式

对用户暴露的四档概念：

- `Flash`
- `Recall`
- `Reconstruct`
- `Reflective`

为避免与 primitive `reflect` 冲突，规范内部对第四档统一记作：

- `reflective_access`

### 4.9.2 各档语义

| 用户侧名称 | 规范内部名称 | 目标 | 典型行为 |
| --- | --- | --- | --- |
| `Flash` | `flash` | 极低延迟、最低访问成本 | 优先近期上下文与少量直接命中对象，不做跨 episode 重构 |
| `Recall` | `recall` | 默认平衡档 | 执行标准 `retrieve -> read -> workspace -> solve` |
| `Reconstruct` | `reconstruct` | 提高复杂问题的记忆覆盖和组织质量 | 允许多对象展开、跨 episode 组合、schema + episodic 联合重建 |
| `Reflective` | `reflective_access` | 在高正确性场景中优先证据完整性和回答校验 | 在 `reconstruct` 基础上增加一致性检查、证据核查和回答前自审 |

### 4.9.3 冻结边界

- 访问档位调节的是“访问深度、展开深度、校验深度”，不是对象真值
- 访问档位默认不要求新增长期对象
- 访问档位可以调用现有 primitive，但不等同于“必须调用 primitive `reflect` 生成 `ReflectionNote`”
- 访问档位不得绕开 budget state

### 4.9.4 `auto` 档

该 addendum 同时冻结一个默认推荐调度模式：

- `auto`

`auto` 的职责是根据任务风险、时延预算、约束强度、历史失败信号和当前覆盖不足情况，动态选择访问档位。

`auto` 必须支持：

- 逐级升级：`flash -> recall -> reconstruct -> reflective_access`
- 逐级降级：在预算紧张、问题简单或已经满足质量要求时退回较浅档位
- 自由跳级：例如 `flash -> reconstruct`、`reflective_access -> recall`
- 用户锁定优先：若用户显式指定档位，则 `auto` 不得覆盖该锁定

### 4.9.5 `auto` 的最小调度规则

该 addendum 只冻结调度方向，不冻结唯一算法：

- 普通对话场景优先 `flash / recall`
- 明显依赖历史多片段组合的任务优先 `recall / reconstruct`
- 高正确性、高约束、高风险任务优先 `reflective_access`
- 若当前档位已满足覆盖与约束要求，应允许降级或提前停止深入访问
- 若当前档位覆盖不足、证据冲突或约束风险升高，应允许升级或跳级

### 4.9.6 评测要求

运行时访问档位后续必须进入独立 benchmark。

至少验证：

- 固定档位下的质量下限
- 固定档位下的性能与成本上限
- `auto` 档在不同任务族上的档位选择是否稳定
- `auto` 档是否能在质量 / 成本之间形成合理 frontier
- 升级、降级和自由跳级是否都可被 trace 和审计

补充约束：

- 访问档位 benchmark 的目标是验证“深度调节是否值得”，而不是只比较谁更慢谁更准
- 后续 formal gate 应同时保留质量指标和性能指标，不能只看其中一侧

---

## 5. Utility Objective

## 5.1 总目标

MIND 的统一目标定义为：

**在受限成本下，最大化未来任务序列中的累计记忆效用。**

## 5.2 代理指标

阶段 A 先冻结可度量 proxy，而不直接假设有完美 reward。

核心代理指标：

| 指标 | 作用 |
| --- | --- |
| `TaskSuccessRate` | 当前与未来任务是否完成得更好 |
| `GoldFactCoverage` | 关键事实是否被覆盖 |
| `ReuseRate` | 已存对象是否在后续任务中被真正复用 |
| `ContextCostRatio` | 当前任务上下文成本相对 baseline 的比例 |
| `MaintenanceCostRatio` | 维护成本相对 baseline 的比例 |
| `PollutionRate` | 新派生对象中失真、冲突、无效对象的比例 |

## 5.3 阶段 A 冻结的综合效用分数

采用 [phase_gates.md](./phase_gates.md) 中定义的 `PrimaryUtilityScore`：

`PUS = 0.55 * TaskSuccessRate + 0.15 * GoldFactCoverage + 0.10 * ReuseRate - 0.10 * ContextCostRatio - 0.05 * MaintenanceCostRatio - 0.05 * PollutionRate`

## 5.4 Utility 解释边界

- `PUS` 是阶段 A 到 G 的统一项目指标
- 它不是未来唯一 possible objective
- 但在当前项目中，后续所有 replay / promotion / archive 决策都应能解释为试图提升 `PUS`

---

## 6. Online Loop

## 6.1 定义

`online loop` 指一次任务处理中必须在主路径上完成的记忆操作。

## 6.2 阶段 A 基线 online loop 与 access-mode 扩展

阶段 A 基线 online loop：

```text
observe_task
-> retrieve
-> read
-> build_workspace
-> solve_task
-> write_raw
-> optional_reflect_stub
```

Post-Phase-G addendum 在不改变基础职责边界的前提下，引入 access mode 调度：

```text
observe_task
-> select_access_mode
-> retrieve
-> read
-> build_workspace
-> solve_task
-> write_raw
-> optional_reflect_stub
```

## 6.3 online loop 允许的操作

- `retrieve`
- `read`
- `write_raw`
- 必要时 `reflect`

## 6.4 online loop 不应承担的操作

- 大规模 replay
- 批量 schema synthesis
- 广泛 promotion
- 大规模 archive / reprioritize
- 任何 `conceal / erase / reshape` 治理动作

前四项属于 offline loop；治理动作属于 `governance / reshape loop`。

## 6.5 online loop 的约束

- 必须预算受控
- 不得依赖离线维护存在才能正确完成当前任务
- 所有在线新增对象必须立即可追溯

Post-Phase-G addendum 补充约束：

- online loop 不得读取 provenance 作为检索过滤、排序或权重调整信号
- `read` 仅在调用方具备 `memory_read_with_provenance` capability 时，才允许附带 provenance 摘要作为观测信息返回
- access mode 可以被用户锁定，也可以由 `auto` 调度
- `auto` 必须保留升级、降级和跳级 trace

---

## 7. Offline Loop

## 7.1 定义

`offline loop` 指不在单次任务主路径中执行的记忆维护与重组操作。

## 7.2 阶段 A 冻结的 offline loop

```text
select_replay_targets
-> replay
-> reconsolidation
-> summarize / synthesize_schema
-> promotion_decision
-> archive / deprecate / reprioritize
```

## 7.3 offline loop 允许的操作

- replay
- reconsolidation
- summarize
- reflect
- reorganize_simple

## 7.4 Reconsolidation 规则

阶段 A 冻结：

- 被修订的对象必须生成新版本
- 原版本必须保留
- 新版本必须继承对象身份并更新 `version`
- 新版本必须保留 `source_refs`

## 7.5 Promotion 规则

阶段 A 不要求实现 promotion，但要求定义准入条件。

默认 promotion criteria：

- `reuse_count >= 2`
- 跨 episode 证据支持
- 无明确冲突
- 预计可提升后续复用或降低成本

promotion 目标：

- `SummaryNote -> SchemaNote`
- `ReflectionNote -> SchemaNote`

## 7.6 Archive / Deprecate 规则

- `archive`：对象弱可见，但保留
- `deprecate`：对象仍存在，但默认不推荐使用
- `invalid`：对象已被证伪或确认为错误

阶段 A 禁止将这些状态变更实现成物理删除。

## 7.7 Post-Phase-G Addendum: Offline Loop 与治理边界

Post-Phase-G addendum 明确：

- offline maintenance 可以做 replay、反思、promotion、archive、reprioritize
- offline maintenance 不得偷渡 provenance 作为 promotion / ranking / retrieval 的优化信号
- offline maintenance 不得替代高权限治理接口执行 `conceal / erase`
- provenance-based 遗忘、重塑和工件清理属于独立的 `governance / reshape loop`

---

## 8. Post-Phase-G Addendum: Governance / Reshape Loop

## 8.1 定义

`governance / reshape loop` 指独立于 online / offline 的高权限主动治理流程。

它的目标不是提升即时 `PUS`，而是：

- 按来源主体、时间窗、环境或保留策略管理记忆
- 执行可恢复或不可恢复的遗忘
- 对 mixed-source 派生对象做细粒度重写
- 清理索引、缓存、评测工件与治理相关副本

### 8.1.1 最小 Capability 边界

MIND 仍然不定义业务系统完整的 RBAC / ABAC 模型，但为了让 provenance 与 governance 接口具备可执行边界，Post-Phase-G addendum 冻结以下最小 capability 切分：

| capability | 允许的动作 |
| --- | --- |
| `memory_read` | 普通 `read / retrieve` |
| `memory_read_with_provenance` | 在 `read` 结果中查看 provenance 摘要 |
| `governance_plan` | 查看 provenance、生成 `plan / preview` |
| `governance_execute` | 执行 `conceal`、执行非 `full` scope 的 `erase`、触发 reshape rewrite |
| `governance_approve_full_erase` | 对 `erase(scope=full)` 执行审批 |

补充约束：

- 这是 MIND 内部执行边界，不等于完整产品权限系统
- 低权限调用方不得通过普通 `read`、日志、报表或评测输出旁路读取高敏 provenance
- `approve` 与 `execute` 默认不应被同一自动化流程静默合并

## 8.2 冻结的执行流程

普通治理流程：

`plan -> preview -> execute`

高风险治理流程：

`plan -> preview -> approve -> execute`

该 addendum 冻结以下规则：

- `erase(scope=full)` 必须进入高风险流程
- 任何 `erase` 至少要有 `preview`
- 所有执行结果都必须落入 `governance_audit`

## 8.3 允许的操作

- 查看 provenance 与 provenance footprint
- `conceal`
- `erase`
- 基于剩余证据重写受影响对象
- 清理索引、副本、缓存与自动生成工件
- 输出治理审计记录

## 8.4 `conceal` 与 `erase` 语义

### `conceal`

- 逻辑不可见
- 默认可恢复
- 保留对象和 provenance，但普通 online / offline 路径不可见
- 必须保留完整治理审计链

### `erase`

- 物理擦除或带 tombstone 的不可恢复删除
- 默认 scope 为 `memory_world_plus_artifacts`
- 必须处理 provenance、索引、副本与自动生成工件
- 若 scope 为 `full`，必须审批

### `erase_scope`

| scope | 含义 |
| --- | --- |
| `memory_world` | 只处理对象、版本、lineage、索引和 provenance 本体 |
| `memory_world_plus_artifacts` | 在 `memory_world` 之外，再处理缓存、trace、评测 JSON、自动生成工件 |
| `full` | 在 `memory_world_plus_artifacts` 之外，再处理报表副本、人工导出物与外部可读副本 |

## 8.5 Mixed-source 对象的重写规则

该 addendum 对 mixed-source 派生对象冻结如下治理语义：

1. 先移除被 `conceal / erase` 命中的 `evidence_refs` 与 `direct_provenance_ids`
2. 再按 `support_rule` 判定每个 `support unit` 的状态
3. `retained / rewritten / dropped` 的结果必须显式记录
4. 父对象必须生成新版本，或在无法保留任何有效单元时被标记为 `invalid` / 删除

补充约束：

- `WorkspaceView` 在 slot 级治理后必须整体重渲染
- `TaskEpisode` 不做局部编辑，只基于剩余 `record_refs` 整体重建
- `RawRecord` 不做局部编辑，只允许整条 `conceal / erase`

## 8.6 Governance 约束

- provenance 默认可以存明文高敏字段，但只允许高权限读取
- provenance 不得进入 runtime retrieval / ranking / weighting
- 所有治理修改都必须版本化或以具名审计记录显式表示
- 不允许 silent governance execution
- `scope=full` 必须显式审批

---

## 9. 三个端到端 Episode 示例

这一节用于满足阶段 A gate 的 `A-5`。

## 示例 1：一次成功的任务回忆

### 场景

用户再次询问上次成功执行过的工具流程。

### state

- `TaskEpisode#12` 已存在
- 若干 `RawRecord` 已存在
- 一个高优先级 `SummaryNote` 已存在
- `priority_state` 表明该 summary 复用过两次

### observation

- 当前任务目标：复用既有成功流程
- 当前 budget 有限

### action

- `retrieve(query=similar_task)`
- `read(object_ids=[SummaryNote, TaskEpisode])`
- 构建 `WorkspaceView`
- 执行任务
- `write_raw` 写入本轮结果

### reward

- 任务成功
- context 成本低于 raw replay baseline
- 既有 summary 被再次复用

## 示例 2：一次失败后的反思与整理

### 场景

Agent 因引用过期信息导致任务失败。

### state

- 当前 episode 刚结束
- workspace 中包含一条过时 `SummaryNote`

### observation

- 任务失败
- failure 原因可定位到过期摘要

### action

- `write_raw`
- `reflect(episode_id)`
- `reorganize_simple(operation=deprecate, target_refs=[old_summary])`
- `summarize(input_refs=[recent_records])`

### reward

- 当前任务失败，但未来污染风险下降
- 旧摘要降权
- 新摘要进入后续候选池

## 示例 3：跨 episode schema 晋升

### 场景

多个任务里都出现同一类成功步骤，系统尝试把局部经验晋升为更稳定 schema。

### state

- `ReflectionNote#4/#7/#11` 均指向相同模式
- `reuse_count` 与 `priority` 持续上升

### observation

- 多个反思对象之间存在共同结构
- 已满足 promotion criteria

### action

- replay 这些反思相关对象
- `reorganize_simple(operation=synthesize_schema, target_refs=[...])`
- 生成 `SchemaNote`
- 更新 priority

### reward

- 后续相似任务可以更快被正确组织
- retrieval space 更紧凑
- schema 成为长期复用对象

---

## 10. 阶段 A 基线与 Post-Phase-G Addendum 结论

当本文的阶段 A 基线部分完成并冻结后，阶段 A 应被视为已经明确了以下前置条件：

- world state 的最小结构
- object schema
- primitive contract
- workspace contract
- utility objective
- online / offline loop
- 3 个端到端 episode 映射示例

这意味着阶段 B 可以开始实现：

- append-only 存储
- source trace
- version graph
- object validator

而不需要继续争论“这个对象到底是什么”“这个 primitive 到底会不会改状态”。

Post-Phase-G addendum 则为后续阶段继续补充了：

- provenance control plane
- governance / reshape loop
- runtime access policy
- governance-ready object projection 与最小 capability 边界

这些内容约束 G 之后的新阶段，但不追溯推翻 A ~ G 的历史验收结论。
