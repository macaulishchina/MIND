# MIND Growth Architecture Plan

## 目标

这份文档重新组织了对 MIND 后续强化方向的建议，目的是在不偏离项目原始设计理念的前提下，给出一套更高维、可协同、可落地、可供其它模型和团队挑战的方案。

本方案默认遵循以下前提：

- MIND 的核心不是“做一个更大的 memory store”
- MIND 的核心是“在不更新模型权重的前提下，让外部记忆持续变得更有用”
- 记忆系统的价值不由存储量定义，而由未来任务效用定义

参考项目内已有设计主线：

- [README.md](../../README.md)
- [design_breakdown.md](../design/design_breakdown.md)

---

## 一、MIND 的高层设计原则

下面这组原则，是后续所有优化建议的约束条件。它们不是独立的口号，而是一个相互配合的系统。

### 1. 原始经验优先，但不等于停留在原始层

MIND 必须保留原始输入、工具调用、事件轨迹和任务历史，避免过早压缩成不可逆表示。

但这不意味着系统只能停在 raw log 层。正确的做法是：

- 原始经验永远保留
- 高层表示在 raw 之上生长
- 高层表示必须能回溯到原始证据

这保证了系统既有可塑性，也有审计性。

### 2. 高层能力应由简单原语组合而来

MIND 不应该把所有高层记忆能力写死成单一大流程，而应保持：

- 写入
- 读取
- 检索
- 摘要
- 反思
- 链接
- 轻量重组

高层对象和复杂行为，应该尽量从这些 primitive 的组合中涌现，而不是完全依赖 hardcode workflow。

### 3. 成长发生在权重之外

MIND 的核心假设不是 continual training，而是 external memory evolution。

因此，真正需要变强的不是基座模型参数，而是：

- 输入理解质量
- 记忆表示质量
- 记忆组织方式
- 运行时访问策略
- 离线维护与晋升策略

### 4. 统一目标必须是未来任务效用

MIND 不能把“更多记忆”“更长上下文”“更多摘要”误认为成长。

统一目标应该是：

> 在成本受限的条件下，最大化未来任务中的累计记忆效用。

这意味着所有机制都要接受下面几个维度的约束：

- 是否提高未来任务成功率
- 是否降低未来任务成本
- 是否提高正确性、稳定性、可解释性
- 是否减少噪声、冲突和记忆污染

### 5. 在线、离线、治理三条循环必须隔离

MIND 后续架构必须显式分离：

- `online loop`：当前任务内的快速使用与小步写回
- `offline maintenance loop`：摘要、反思、重组、晋升、优先级调整
- `governance loop`：来源治理、隐藏、删除、重塑

如果三者混在一起，系统会出现：

- 查询路径过重
- 写入污染治理边界
- 高权限动作侵入日常优化

### 6. 工作记忆必须是有限句柄集合

MIND 不应该把“可查询的一切”直接等同于“当前任务可操作的一切”。

真正关键的是：

- 候选记忆很多
- 当前任务真正可操作的上下文必须很少
- 系统必须明确地做 gating、slot selection、priority control

因此，workspace / working memory index 应始终被视作“有限句柄集合”，而不是“无限拼接上下文”。

### 7. LLM 参与应是高杠杆、可验证、分层的

MIND 不应把 LLM 变成一个无处不在的黑箱。

更合理的原则是：

- 让 LLM 参与高杠杆环节
- 所有关键输出尽量结构化
- 高价值写入必须带 verifier
- 对吞吐和成本敏感的场景，要有非 LLM 路线

### 8. MIND 应该使用 RAG，但不应该等于 RAG

RAG 可以是 MIND 的一个重要子能力，尤其适合候选召回、证据组织和长文档访问。

但 MIND 的定义比 RAG 更大，因为它还包括：

- 写回
- 反思
- 重组
- 晋升
- 记忆策略优化

---

## 二、阶段化优化建议

下面按 `输入 -> 存储 -> 输出（查询）` 三个阶段展开建议。

排序规则：

- 优先级：`P0 > P1 > P2`
- 风险：`低 / 中 / 高`
- 排序尽量反映“重要性优先”

---

## 三、输入阶段

### 阶段目标

输入阶段的目标不是“把东西存进去”。

它真正要做的是：

- 保真接收原始经验
- 识别高价值信号
- 判断是否需要结构化
- 为后续存储与访问创造更好的起点

### P0-1 输入分流器（Ingest Triage）

- 优先级：`P0`
- 风险：`中`

建议：

- 在原始写入之前增加一个输入分流层
- 先判断一条输入属于哪种类型：
  - 普通原始记录
  - 结构化候选
  - 冲突更新
  - 重复信息
  - 值得异步整理的高价值样本

原理：

- 不是所有输入都值得同样对待
- 如果没有 triage，系统会把高价值信号和噪声平等地塞进同一层
- 后续检索和 access 会因此被噪声拖垮

与设计原则的关系：

- 遵循“原始经验优先”
- 也遵循“未来效用优先”

推荐实现：

- 同步路径只负责 raw ingest
- 异步路径负责结构化判断和后续任务派发

### P0-2 双通道输入：Raw + Structured Proposal

- 优先级：`P0`
- 风险：`高`

建议：

- 所有输入都先写入 `RawRecord`
- 同时异步生成结构化候选：
  - `EntityNode`
  - `LinkEdge`
  - `TaskEpisode`
  - 未来的 `PreferenceNote / PolicyNote / ValueNote`

原理：

- raw 层解决保真与审计
- structured 层解决后续可检索、可组织、可晋升
- 二者不能互相替代

推荐实现：

- 结构化候选不要直接 commit
- 先记录为 proposal
- 通过 evidence verifier 后再转正式对象

风险说明：

- 如果让 LLM 直接写正式对象，吞吐越大，污染越快

### P1-1 输入冲突检测与更新识别

- 优先级：`P1`
- 风险：`中`

建议：

- 输入时做一次轻量 recall
- 判断新输入与已有记忆的关系：
  - duplicate
  - refine
  - contradict
  - supersede

原理：

- “这是一条新记忆”与“这是旧记忆的修正”是两种完全不同的动作
- 不在输入时做更新识别，后续就只能靠查询阶段被动发现冲突

推荐算法：

- lexical / dense hybrid retrieval 找近邻
- 分类器或小模型做关系判别
- 高风险样本进入离线核验

### P1-2 输入价值评估与新颖性评估

- 优先级：`P1`
- 风险：`中`

建议：

- 在输入侧为对象打早期信号：
  - novelty
  - estimated future utility
  - self-relevance
  - cross-task relevance
  - fragility

原理：

- 存储阶段和离线 replay 需要这些信号做调度
- 如果输入时完全不打标，后续只能盲目 replay 或盲目晋升

### P1-3 团队高吞吐场景下的输入架构

- 优先级：`P1`
- 风险：`中`

建议：

- 所有输入都走 append-only log
- 使用批处理和异步队列
- 做 source-aware routing：
  - human chat
  - tool logs
  - CI / system logs
  - docs / ticket / design artifacts

原理：

- 高吞吐下，同步逐条处理不可运营
- 来源不同，后续整理方式也不同

### P2-1 输入阶段的噪声抑制与去重

- 优先级：`P2`
- 风险：`低`

建议：

- 增加 hash-based dedup
- 增加 boilerplate log suppression
- 增加 repeated tool output compaction

原理：

- 这些是工程化细节，但对长期记忆质量非常重要

---

## 四、存储阶段

### 阶段目标

存储阶段不应只是“把数据持久化”。

它真正的任务是：

- 把原始经验组织成可成长的 memory world
- 允许多层表示并存
- 让被使用的记忆继续变化

### P0-1 从单层对象表走向多层记忆系统

- 优先级：`P0`
- 风险：`高`

建议：

- 显式区分以下层次：
  - `Episodic Fast Store`
  - `Semantic / Schema Store`
  - `Procedural / Policy Store`
  - `Value / Persona Store`

原理：

- 不同记忆类型的更新频率、可靠性、检索方式都不同
- 如果全部都混在一个统一对象池里，系统很难做稳定策略

说明：

- 当前 MIND 已有 `RawRecord / SummaryNote / ReflectionNote / SchemaNote`
- 但 `procedural/policy/value/persona` 还没有真正成为一等存储层

### P0-2 把 Utility Objective 落成正式字段和调度依据

- 优先级：`P0`
- 风险：`高`

建议：

- 为对象显式维护：
  - `future_utility`
  - `confidence`
  - `reuse_count`
  - `contradiction_count`
  - `decay`
  - `fragility`
  - `promotion_score`
  - `archive_score`

原理：

- 没有统一记忆效用信号，系统只会越存越多
- 也无法把 offline maintenance、replay、promotion、forgetting 统一起来

### P0-3 Promotion Pipeline：Proposal -> Verify -> Commit

- 优先级：`P0`
- 风险：`高`

建议：

- 所有高层派生对象，尤其是 `SchemaNote / PolicyNote / ValueNote`
- 都采用三段式：
  - proposal
  - evidence verification
  - commit

原理：

- 单次 LLM 抽象很容易产生“看起来合理但没证据”的伪结构
- 记忆系统一旦被高层伪结构污染，后续会不断自我强化错误

推荐实现：

- proposer 负责提出候选 schema/policy
- verifier 检查是否有跨 episode 支撑、是否有反证、是否覆盖来源
- commit 只写通过验证的对象

### P1-1 Reconsolidation 机制

- 优先级：`P1`
- 风险：`中高`

建议：

- 记忆被取回、修订、验证后，应倾向于生成新版本
- 不要把记忆视为只读事实

原理：

- 人类记忆的重要机制之一不是静态保存，而是被激活后重新可塑
- MIND 若要成长，必须允许“使用后的再固化”

具体收益：

- 让高价值记忆越用越稳
- 让冲突和修正进入版本链
- 让后续访问拿到更成熟对象

### P1-2 Priority Replay 与离线维护调度器

- 优先级：`P1`
- 风险：`中`

建议：

- offline maintenance 不应平均处理所有对象
- 应优先处理：
  - 高价值但不稳定的对象
  - 高频复用对象
  - 冲突多发对象
  - 最近关键失败相关对象

原理：

- replay 如果没有优先级，只会变成昂贵的后台扫描
- 记忆成长应该是 selective strengthening

### P1-3 更强的表征层：Embedding、Graph、Cluster、Topic

- 优先级：`P1`
- 风险：`中`

建议：

- 在现有 lexical + deterministic embedding 基础上升级为：
  - 更强 dense embedding
  - graph relation memory
  - topic clustering
  - contradiction graph

原理：

- LLM 不适合独自承担所有“记忆结构理解”
- 很多结构问题更适合传统 IR / graph / clustering 方法

### P2-1 工程化存储改进

- 优先级：`P2`
- 风险：`低`

建议：

- hot/cold tier
- 分租户分区
- 物化索引
- async compaction
- derived object refresh job

原理：

- 大吞吐团队场景下，这是运行成本和稳定性的前提

---

## 五、输出（查询）阶段

### 阶段目标

输出阶段不应被理解为“问模型一个问题然后生成一段话”。

它真正要完成的是：

- 判断这次任务需要什么记忆
- 决定访问多深
- 组织有限工作记忆
- 生成答案
- 必要时触发写回和整理

### P0-1 增加 Memory Planner / Controller

- 优先级：`P0`
- 风险：`中高`

建议：

- 在 `retrieve` 之前增加一个规划层，负责决定：
  - 查 episodic 还是 schema 还是 policy
  - 是否需要跨 episode
  - 选择浅/深 access mode
  - 是否需要先 query rewrite
  - 是否应拆成多个子问题

原理：

- 现在的 access depth 已经是一个好起点
- 但它还更像 runtime policy family，而不是完整 memory planner

### P0-2 Hybrid Retrieval，而不是单一召回逻辑

- 优先级：`P0`
- 风险：`中`

建议：

- 候选生成使用混合检索：
  - lexical
  - dense
  - graph walk
  - episode anchor
  - priority / reuse / recency
  - structured artifact tree navigation

原理：

- 没有哪一种 retrieval 对所有记忆类型都最好
- MIND 的记忆对象本来就是异构的

### P1-1 强化 Workspace Selection

- 优先级：`P1`
- 风险：`中`

建议：

- workspace builder 不应只看 retrieval score 和 priority
- 应显式平衡：
  - raw evidence vs summary evidence
  - supporting evidence vs conflicting evidence
  - recent episode vs stable schema
  - local detail vs global rule

原理：

- 决定回答质量的往往不是召回本身，而是哪些对象进入有限工作记忆

### P1-2 查询后写回（Post-Query Writeback）

- 优先级：`P1`
- 风险：`高`

建议：

- 一次查询如果暴露出：
  - 冲突
  - 缺口
  - 高价值失败模式
  - 新稳定偏好
  - 值得保留的 reasoning trace

  应该触发：

- reflect
- summarize
- promote
- update priority
- enqueue offline maintenance

原理：

- 没有 post-query writeback，系统只有消费，没有成长

### P1-3 回答生成采用多阶段结构

- 优先级：`P1`
- 风险：`中高`

建议：

- 将回答过程拆成：
  - planning
  - evidence compression
  - answer drafting
  - answer verification

原理：

- 让一个模型同时做规划、压缩、回答、校验，往往质量不稳定
- 分工后更可控，也更便于吞吐优化

### P2-1 面向团队高吞吐的查询工程化设计

- 优先级：`P2`
- 风险：`中`

建议：

- workspace cache
- answer cache
- query normalization cache
- shallow/deep 分级路由
- 失败快速回退

原理：

- 团队级吞吐下，如果所有请求都走最深 access + 最大模型，系统无法运营

---

## 六、工程化建议（跨阶段）

下面这些点不改变设计哲学，但对落地非常重要。

### 1. 明确同步路径与异步路径

- 同步路径：
  - raw ingest
  - cheap retrieval
  - fast access

- 异步路径：
  - structure extraction
  - summarize
  - reflect
  - promotion
  - replay
  - compaction

### 2. 明确 proposal object 与 committed object 的边界

建议引入 proposal lifecycle：

- proposed
- verified
- committed
- rejected

高吞吐下，这个边界能极大减少高层记忆污染。

### 3. 做对象级和链路级 trace

每个高层对象都应能回答：

- 来自哪些原始证据
- 由哪次模型调用提出
- 是否被 verifier 通过
- 是否被未来任务复用

### 4. 为“高价值但高风险”路径保留人工 review 入口

适合人工 review 的对象：

- Policy / Procedural memory
- Value / Persona related memory
- Cross-tenant or sensitive schema

### 5. 把评测嵌进系统设计，而不是事后补

对每项改动都应追问：

- 提高了哪些长期指标
- 降低了哪些成本
- 是否增加了污染率
- 是否改变了 access frontier

---

## 七、LLM 如何使用，如何参与

## 总原则

LLM 不应只是最终的回答器。

在 MIND 里，LLM 更适合扮演这些角色：

- 输入理解器
- 结构提议器
- 离线反思器
- 查询规划器
- 证据压缩器
- 答案起草器
- 校验器

更重要的是：

- 不同角色不一定由同一个模型承担
- 不同角色也不一定都需要 LLM

### 按重要性排序的建议

### P0-1 用 LLM 做 Proposal，不直接做 Final Truth

- 风险：`低到中`

原则：

- LLM 适合提出候选结构
- 不适合在高吞吐系统里直接定义正式记忆真相

### P0-2 分层模型路由

- 风险：`中`

建议：

- 规则 / 检索 / 分类器
- 小模型
- 中模型
- 大模型

各自承担不同任务：

- 小模型：triage、rewrite、分类
- 中模型：summarize、reflect、evidence compression
- 大模型：policy/schema synthesis、high-stakes answering、verifier

### P0-3 把 LLM 调用重点放到高杠杆节点

高杠杆节点包括：

- 输入结构抽取
- 离线反思
- schema / policy synthesis
- memory planner
- answer verification

而不是把主要预算都花在最后一跳回答上。

### P1-1 高吞吐条件下的 LLM 体系

- 风险：`中高`

建议：

- 异步批处理
- 多队列优先级调度
- per-tenant quota
- fallback policy
- 模型分级 SLA

需要特别避免：

- 所有写入都同步等 LLM
- 所有查询都强制 deep reasoning
- 所有高层派生都走同一大模型

### P1-2 LLM 输出必须结构化

- 风险：`低`

建议：

- 输出 typed proposal
- 显式携带 evidence refs
- 输出 confidence / uncertainty / contradiction candidates

### P1-3 增加 LLM Verifier

- 风险：`中高`

建议：

- 对 schema/policy/value memory 进行二次校验
- 检查：
  - 是否真的被证据支持
  - 是否忽略反证
  - 是否跨 episode 稳定
  - 是否污染已有结构

---

## 八、除了 LLM，还有没有其它 AI 算法可以利用

答案是：不仅可以，而且非常值得。

以下算法在 MIND 中有很强的价值：

### 1. Embedding Retrieval

适用阶段：

- 输入近邻比较
- 存储索引
- 输出候选召回

### 2. Cross-Encoder / Reranker

适用阶段：

- 查询阶段候选重排
- 输入冲突识别

### 3. 图算法 / Graph Walk

适用阶段：

- LinkEdge / EntityNode 导航
- 跨对象关系扩展
- 反证追踪

### 4. 聚类 / 主题发现

适用阶段：

- 离线 maintenance
- schema candidate grouping
- long-horizon memory compression

### 5. 异常检测 / 冲突检测

适用阶段：

- 输入阶段
- reconsolidation 阶段
- 高层 schema 审计

### 6. Multi-Armed Bandit / RL / Policy Optimization

适用阶段：

- replay 调度
- access mode 选择
- memory budget allocation

### 7. 生存分析 / 衰减模型

适用阶段：

- forgetting
- archive / reprioritize
- stale memory management

结论：

- LLM 是 MIND 里的核心能力之一
- 但绝不是唯一的“智能部件”
- 很多记忆系统问题，更适合 IR、图算法、聚类、排序、调度算法

---

## 九、RAG 是否可以用于 MIND

答案：可以，而且应该用，但只能作为子能力。

### 输入阶段

可以用 RAG 做：

- duplicate detection
- update detection
- contradiction lookup

### 存储阶段

可以用 RAG 做：

- summarize / reflect 的证据收集
- schema candidate evidence gathering

### 输出阶段

这是最自然的使用位置：

- 候选召回
- 证据组织
- workspace 构建
- answer support selection

### 但必须强调

MIND 不应退化成：

`top-k chunk -> prompt -> answer`

因为 MIND 还必须包含：

- 写回
- 反思
- 晋升
- 重组
- utility optimization

一句话总结：

> MIND 应该使用 RAG，但不应该等于 RAG。

---

## 十、PageIndex 思路可以借鉴什么

这一部分给出的是“思路级”判断，而不是对某个具体实现细节的强绑定复刻。

### 可借鉴的核心思想

### 1. 结构优先，而不是 chunk 优先

如果 PageIndex 的核心思想是：

- 先给长文档或长上下文建立层级结构
- 再沿结构做导航式访问

那么这对 MIND 很有借鉴意义。

MIND 当前的 retrieval / workspace 已经在朝“组织”迈出一步，但对长结构化 artifact 还可以更进一步。

### 2. 检索不只是一次 top-k，而是分层导航

这很适合：

- 长设计文档
- 长会议纪要
- 长任务 episode
- 代码仓级 artifact memory

而不只是短聊天消息。

### 3. 结构化 artifact memory 可以成为 MIND 的专用子通道

建议：

- 不要让 PageIndex 思路替换全部 retrieval
- 而是把它作为下面这类对象的专用访问路径：
  - 文档
  - 代码库
  - 报告
  - 长任务记录

### 值得借鉴的实现方向

- 为长对象建立树状索引
- 节点级 evidence trace
- 结构化 expand / collapse
- tree-guided retrieval
- tree-guided workspace construction

### 风险

- 风险等级：`中高`

原因：

- 索引构建成本更高
- 更新代价更高
- 跨文档融合更复杂
- 团队吞吐下需要额外缓存和索引刷新策略

### 最稳妥的采用方式

- 作为 `structured artifact memory` 子系统先试点
- 先服务“长且结构稳定”的对象
- 不直接替换全部 memory retrieval

---

## 十一、总排序：建议优先级矩阵

### 第一优先级（先做）

1. 定义并落地 `memory utility objective`
2. 建立 `ingest triage`
3. 建立 `Raw + Structured Proposal` 双通道输入
4. 建立 `proposal -> verify -> commit` promotion pipeline
5. 为输出阶段增加 `memory planner`
6. 建立查询后写回闭环

### 第二优先级（随后做）

1. 引入多层记忆存储
2. 引入 reconsolidation
3. 引入 hybrid retrieval
4. 引入 stronger workspace selection
5. 引入多模型分层路由
6. 引入 priority replay

### 第三优先级（在系统稳定后做）

1. policy/value/persona memory
2. PageIndex 风格的 structured artifact memory
3. bandit / RL 式调度优化
4. forgetting / decay / archival 策略系统化

---

## 十二、最关键的结论

如果要用一句话概括这份计划：

> MIND 真正该强化的，不是“更会查”，也不是“更会答”，而是“更会经营自己的记忆”。

最不该偏离的 3 条结论是：

1. MIND 的核心不是更大的检索层，而是更完整的记忆演化闭环。
2. LLM 最该参与的是高杠杆记忆环节，而不是所有环节同步硬上。
3. RAG 应该是 MIND 的重要组件，但不应该成为 MIND 的定义。

