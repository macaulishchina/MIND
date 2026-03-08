# MIND 设计拆解与前期实施指南

## 0. 这份文档的目标

这份文档不是论文，也不是功能清单。

它的目标只有一个：把 MIND 从“一个很强的想法”拆成“可以分阶段推进的系统设计与前期工作计划”。

文档会重点回答 5 个问题：

- MIND 到底在做什么
- 它和普通 memory / RAG 的根本区别是什么
- 这个系统的核心架构应该怎么理解
- 前期应该按什么顺序推进
- 每个阶段为什么必要、重点在哪、难点在哪、预计要投入多少精力

说明：

- 这里故意忽略了一些不重要或过早的细节
- 精力预估以“研究原型”为前提，不按生产级系统估算
- 默认团队规模按 1 名主力工程师 + 1 名设计/研究协作者 来理解

## 0.1 一页总览

| 问题 | MIND 的回答 |
| --- | --- |
| 这是什么 | 一个可演化的外部记忆环境，不只是记忆库 |
| 核心目标 | 在不改模型权重的前提下，让记忆随着任务持续变得更有用 |
| 和普通 RAG 的区别 | 不只检索，还允许写回、反思、重组、归档、离线整理 |
| 最关键结构 | `Working Memory Index + Episodic Store + Semantic Store + Procedural Store + Offline Maintenance Loop` |
| 前期最重要的事 | 先跑通“记录 -> 检索 -> 工作视图 -> 反思 -> 离线整理 -> 再利用”的闭环 |
| 第一版最容易做错的地方 | 一开始就做成复杂知识库，或者退化成复杂版 RAG |
| 最小验证目标 | 连续任务中，后续任务的成本或效果因记忆整理而改善 |

阅读建议：

- 第一次读：先看 `0.1 -> 5.4 -> 5.5 -> 8.1 -> 12`
- 要开设计会：重点看 `5.5 / 8.1 / 11`
- 要开始实现：重点看 `8 / 11 / 13`

---

## 1. 用一句话理解 MIND

MIND 要做的，不是一个“帮 LLM 查资料”的记忆库，而是一个“允许 LLM 持续经营、重组和优化自身外部记忆”的环境。

更直接一点说：

普通系统是在问“怎么把相关内容找回来”；
MIND 在问“怎么让记忆本身随着任务不断变得更有用”。

---

## 2. MIND 的核心主张

MIND 的核心主张可以压缩成四句话：

1. 模型权重会停止更新，但记忆不应该停止成长。
2. 不要过早把经验压缩成工程师预设好的结构。
3. 应该给模型一组基础记忆原语，而不是一条写死的记忆流程。
4. 记忆系统的好坏，要看它是否能在长期任务里持续提高收益并控制成本。

这意味着，MIND 真正关注的是“记忆演化”，不是“记忆存储”。

---

## 3. 它和普通 RAG / Memory 模块的区别

普通 RAG 的基本逻辑是：

- 切块
- 建索引
- 召回
- 拼接上下文

这类系统当然有价值，但它的重点是“检索是否命中”。

MIND 想解决的问题更进一步：

- 记忆可以新增
- 记忆可以摘要
- 记忆可以链接
- 记忆可以拆分、合并、降权、归档
- 记忆可以被反思和重组
- 这些结构变化会影响后续任务表现

所以，MIND 更像一个“外部可塑认知环境”，而不是一个“检索服务”。

如果这个区别不守住，项目最终很容易退化成“包装更复杂的 RAG”。

---

## 4. 系统应该怎样理解

## 4.1 一个更清晰的抽象

MIND 可以被理解为下面这个闭环：

`任务到来 -> 观察记忆世界 -> 检索和组织 -> 完成任务 -> 评估记忆是否有效 -> 写回经验与反思 -> 重组记忆结构 -> 服务后续任务`

这条闭环比任何单个模块都重要。

因为 MIND 的重点从来不是“某次召回做得多漂亮”，而是“系统有没有随着任务序列变得更会记、更会用、成本更低”。

## 4.2 系统里真正要设计的对象

从工程角度看，MIND 不是一个对象，而是 5 个对象一起工作：

| 对象 | 它是什么 | 为什么重要 |
| --- | --- | --- |
| `Memory World` | 外部可编辑的记忆环境 | 给 Agent 一个可操作的外部认知空间 |
| `Memory Objects` | 系统里的基本记忆单位 | 决定记忆能否被追踪、引用、重组 |
| `Primitive Operations` | Agent 可执行的最小记忆动作 | 决定系统是“可操作”而不只是“可存储” |
| `Utility Objective` | 衡量记忆系统是否变好的统一目标 | 防止系统只会越存越多 |
| `Growth Loop` | 使用、反馈、写回、重组、再使用的闭环 | 决定系统能否真正成长 |

### 1. Memory World

外部记忆环境本身，里面包含：

- 原始经验
- 派生表示
- 对象关系
- 检索索引
- 状态和版本
- 成本与预算

### 2. Memory Objects

系统里的基本记忆单位，例如：

- 原始对话记录
- 工具调用轨迹
- 任务 episode
- 派生摘要
- 反思笔记
- 实体节点
- 关系边
- 当前任务工作视图

### 3. Primitive Operations

模型可以对记忆世界执行的基础动作，例如：

- `read`
- `write`
- `retrieve`
- `summarize`
- `link`
- `split`
- `merge`
- `reflect`
- `reorganize`
- `archive`
- `evaluate`

### 4. Utility Objective

系统的统一目标：

在成本受限的条件下，最大化未来任务中的累计记忆效用。

### 5. Growth Loop

让系统真正发生成长的机制：

- 使用
- 反馈
- 写回
- 重组
- 再使用

没有这 5 个对象的完整闭环，MIND 就不成立。

## 4.3 一个重要补充：MIND 也应该吸收认知系统约束

MIND 不是要“模拟大脑”，但它非常适合借鉴生物记忆系统里那些已经被反复验证的约束和机制。

原因很简单：

- 人类记忆不是一个平铺的大仓库，而是分层、限速、分时处理的
- 有些记忆在线快速可用，有些记忆只能离线整理
- 有些记忆会变得稳定，有些记忆会衰退，有些记忆会被主动压制
- 记忆的重要性并不均匀，系统会优先处理弱但关键、或新颖且高价值的信息

这对 MIND 的启发很直接：

- MIND 不应只有一个统一 memory store
- MIND 不应只有在线检索，没有离线整理
- MIND 不应只考虑“如何记住”，也要考虑“如何不让噪声占满系统”
- MIND 不应把所有记忆对象看作同一种东西

下面的架构建议，会把这些认知约束真正落到系统设计里。

---

## 5. 架构设计：前期应该怎样搭

为了便于实现，建议把架构分成两层来理解：数据层和控制层。

## 5.1 数据层：记忆到底存成什么

建议坚持三层结构。

### 原始经验层

存最原始、最少加工的材料：

- 用户输入
- Agent 输出
- 工具调用和结果
- 任务目标
- 成败结果
- 时间顺序

这一层的价值是：

- 高保真
- 可回放
- 可追溯
- 不会因为早期建模错误把未来上限锁死

### 可塑表示层

存模型自己逐步构建出来的中间结构：

- 摘要
- 标签
- 关系图
- 实体
- 局部索引
- 任务经验
- 反思结果

这一层的价值是：

- 降低后续检索和推理成本
- 让系统可以逐步形成更好结构
- 给“重组”和“演化”提供抓手

### 工作视图层

存为当前任务临时构造出来的可执行记忆视图。

它不是长期知识库，而是当前任务的“记忆工作台”。

这一层的价值是：

- 控制 token 成本
- 把杂乱记忆压缩成当前任务可用的上下文
- 让系统有能力面向任务组织记忆，而不只是被动召回

## 5.2 控制层：谁在驱动记忆演化

控制层至少需要 7 个模块：

### 1. Ingestion / Logging

负责把原始交互和工具轨迹写入系统。

### 2. Primitive Engine

负责执行记忆原语，把 LLM 的操作请求落到数据层。

### 3. Retrieval + Workspace Builder

负责为当前任务检索候选记忆，并构造工作视图。

### 4. Evaluator

负责评估本次任务中哪些记忆真正有帮助，哪些操作值得保留。

### 5. Reorganizer / Reflector

负责在任务结束后写回反思，并对记忆结构做轻量重组。

### 6. Offline Maintenance

负责在“非当前任务时段”做离线记忆维护。

它的职责不是回答当前问题，而是：

- 重放近期 episode
- 强化高价值记忆
- 压缩弱但重要的经验
- 建立跨任务链接
- 生成更抽象的中间表示

### 7. Forgetting / Priority Manager

负责做优先级调整、降权、归档和可恢复抑制。

它的价值在于防止系统无限堆积，并让“记忆可用性”随着时间和反馈动态变化。

## 5.3 一条建议的最小运行流程

MIND v0 建议按下面这条路径跑起来：

1. 记录任务全过程
2. 以多路检索拿到候选记忆
3. 构建当前任务工作视图
4. 让 Agent 基于该视图执行任务
5. 记录任务结果与代价
6. 生成任务后反思
7. 将反思和必要摘要写回表示层
8. 在离线阶段触发 replay / maintenance
9. 对明显冗余或失效结构做轻量重组或降权
10. 将更新后的结构服务给后续任务

只要这条链能稳定跑起来，MIND 的核心命题就已经进入可实验状态。

## 5.4 认知启发：只保留能落地的 5 条

这一节不再使用拟人化或病理类比。

这里只保留那些可以直接映射到：

- 系统结构
- 调度策略
- 数据字段
- 评测指标

的认知启发。

| 启发 | 简化理解 | 对 MIND 的设计要求 |
| --- | --- | --- |
| 有限工作集 | 当前任务真正能直接操作的只是少量句柄 | `workspace view` 必须限槽位、句柄化 |
| 快速情景 + 慢速沉淀 | 新经验和稳定知识不该混在一个池子里 | 区分 episodic / semantic / procedural |
| 在线执行 + 离线维护 | 不是所有记忆处理都应发生在任务内 | 必须有 `offline maintenance loop` |
| 取回后可再固化 | 记忆被使用后应允许修订和晋升 | 引入 `reconsolidation + promotion policy` |
| 遗忘与重放都应有优先级 | 系统不能平均对待所有记忆 | 引入 priority score、archive、priority replay |

### 启发 1：工作记忆应被实现成“有限句柄集合”

对 MIND 来说，真正重要的不是人类工作记忆到底是 4 还是 7，而是：

- 当前任务可直接操作的对象数必须有限
- 工作区应该保存“句柄”，不是整块原文
- 每个句柄都应支持展开、替换和追溯

对 MIND 的直接要求：

- `workspace view` 必须是索引层，不是堆料层
- `workspace view` 要有明确槽位预算 `K`
- `K` 应视为实验超参数，而不是照搬人类数字

工程建议：

- v0 先把 `workspace view` 设计成固定槽位
- 每个槽位存 `summary + evidence refs + source refs + priority`
- 优先优化“怎么选入槽位”，而不是一味扩大上下文

### 启发 2：新经验和稳定知识应分层存放

高保真新经验、长期稳定知识、以及“怎么做”的经验，应该分层处理。

对 MIND 的直接要求：

- 新写入内容先进入 `episodic store`
- 高频复用、跨任务稳定的内容再晋升到 `semantic / schema store`
- 可重复执行的方法和规则再沉淀到 `procedural / policy store`

这里还应引入一个很实用的设计原则：

- 写入时更强调 `pattern separation`
- 召回时更允许 `pattern completion`

也就是：

- 存的时候尽量避免把相似 episode 过早糊成一团
- 取的时候允许用不完整线索补出相关结构

工程建议：

- episodic 层优先保留差异和上下文
- semantic 层优先保留稳定共性
- procedural 层优先保留“下次怎么做”

### 启发 3：在线使用和离线维护必须拆开

很多记忆操作不适合塞进单次任务路径里。

对 MIND 的直接要求：

- 任务内只做必要的检索、组织和最小写回
- 较重的 replay、压缩、合并、晋升、归档应放到离线窗口
- 离线维护应是正式模块，不是后期补丁

工程建议：

- 用 `offline maintenance window` 代替“睡眠”这类表述
- 明确哪些操作属于 online loop，哪些属于 offline loop
- 评测时比较“有无离线维护”的差异

### 启发 4：记忆被取回后，应该进入可修订状态

比“做梦”更有工程价值的概念是 `reconsolidation`。

它对 MIND 的启发是：

- 记忆不应被视为只读事实
- 一条记忆被再次取回、验证、修正后，应生成新版本
- 取回后的更新最好是版本化更新，而不是原地覆盖

这还引出一个关键机制：`promotion policy`

也就是：

- 什么样的 episodic 经验值得晋升为 semantic schema
- 什么样的 repeated successful behavior 值得晋升为 procedural policy

工程建议：

- 所有被修改的对象都保留版本链
- 引入 `promotion criteria`，例如复用次数、跨任务稳定性、收益提升、冲突率下降
- 可选加入 `schema synthesis`，但必须带证据校验，不能把它写成自由联想模块

### 启发 5：遗忘和 replay 都应该被优先级驱动

一个可成长系统既不能平均保存所有东西，也不能平均 replay 所有东西。

对 MIND 的直接要求：

- 检索优先级要动态调整
- replay 队列要可排序
- 遗忘优先做降权、抑制和归档，而不是硬删除

工程建议：

- 给对象维护 `priority score`
- score 可以由 `importance × fragility × expected_future_utility` 近似
- 前期先做 `archive / deprecate / suppress-from-retrieval`
- replay 调度优先考虑“高价值但易丢失”以及“多次复用、值得晋升”的对象

## 5.5 据此推荐的 MIND 架构增补

如果吸收上面的认知启发，MIND 的推荐结构不应只是“三层记忆”，而应是“多层记忆 + 在线/离线双循环”。

建议补成下面 6 个功能结构：

### 1. Working Memory Index

对应当前任务中的快速操作区。

特点：

- 槽位有限
- 保存的是结构化句柄，不是完整原文
- 支持快速展开与替换

### 2. Episodic Fast Store

对应高保真的近期经验层。

特点：

- 写入快
- 基本不丢原始上下文
- 易于 replay
- 容易脆弱和冗余

### 3. Semantic / Schema Store

对应慢速沉淀出的稳定知识层。

特点：

- 来自多次 episode 的抽象
- 结构更稳定
- 更适合长期复用
- 不追求保留全部细节

### 4. Procedural / Policy Store

对应“怎么做”的经验层。

这层不只是知识，而是：

- 任务策略
- 工具使用模式
- 常用流程
- 失败规避规则

### 5. Priority Tags

对应“这条记忆为什么重要”。

这里不使用“情绪模块”的说法，直接落成优先级信号：

- 新颖度
- 失败代价
- 未来相关性
- 使用频率
- 奖励或惩罚强度

### 6. Offline Maintenance Loop

负责做 replay、reconsolidation、promotion、归档和优先级更新。

## 5.5.1 架构速查表

| 结构 | 近似生物类比 | 在 MIND 中负责什么 | 前期是否必须 |
| --- | --- | --- | --- |
| `Working Memory Index` | 工作记忆 / 注意焦点 | 当前任务的少量快速索引句柄 | 是 |
| `Episodic Fast Store` | 海马式近期情景记忆 | 保留高保真 recent episodes | 是 |
| `Semantic / Schema Store` | 皮层式长期语义结构 | 沉淀稳定知识和 schema | 是 |
| `Procedural / Policy Store` | 程序性记忆 | 保留“怎么做”的经验 | 建议尽早预留 |
| `Priority Tags` | 价值 / 显著性信号 | 决定保留、检索、replay 优先级 | 是 |
| `Offline Maintenance Loop` | replay / maintenance | 做离线重放、再固化、晋升、归档 | 是 |

## 5.5.2 推荐架构图

```mermaid
flowchart LR
    T[当前任务] --> W[Working Memory Index]
    W --> E[Episodic Fast Store]
    W --> S[Semantic / Schema Store]
    W --> P[Procedural / Policy Store]
    T --> L[Ingestion / Logging]
    L --> E
    E --> R[Reflector / Reorganizer]
    R --> O[Offline Maintenance]
    O --> S
    O --> P
    O --> G[Forgetting / Priority Manager]
    G --> E
    G --> S
    G --> P
```

## 5.5.3 两条必须显式设计的控制规则

| 规则 | 含义 | 工程落点 |
| --- | --- | --- |
| `Reconsolidation` | 被取回并修订的记忆生成新版本，而不是原地覆盖 | 版本链、source trace、冲突处理 |
| `Promotion Policy` | 只有满足条件的 episodic 经验才晋升为 semantic / procedural | 复用阈值、稳定性阈值、收益阈值 |

## 5.6 一条更可落地的运行主线

MIND 后续可以按这条主线理解：

`在线任务 -> 有限工作记忆索引 -> 访问 episodic / semantic / procedural 记忆 -> 完成任务 -> 写入新 episode -> 离线 replay -> reconsolidation -> schema / policy promotion -> 归档和优先级更新 -> 服务未来任务`

这比单纯的“三层存储”更接近一个真正可成长的记忆系统。

---

## 6. 架构演化：建议分三代看

为了避免一开始就想做“完全体”，建议从架构演化角度理解项目。

## v0：可运行的记忆闭环

目标不是聪明，而是完整。

需要做到：

- 原始经验可持续记录
- 可以检索
- 可以构建带槽位限制的工作视图
- 可以任务后反思
- 可以触发最小离线整理
- 可以写回派生表示

这一代主要验证：

“记忆闭环能否跑通”

## v1：可重组的记忆系统

在 v0 基础上加入：

- 更明确的对象模型
- 更丰富的关系结构
- 更稳定的反思和重组策略
- 更明确的成本约束
- 更明确的 episodic / semantic / procedural 区分
- 更稳定的 offline replay / maintenance

这一代主要验证：

“系统能否通过结构变化变得更有用，而不只是越存越多”

## v2：可优化的记忆策略

在 v1 基础上继续做：

- 基于反馈改进操作选择
- 基于历史日志优化记忆策略
- 比较不同策略在相同预算下的表现
- 对 replay、重组、遗忘和工作记忆分配做联合优化

这一代主要验证：

“系统能否学会更好的记忆使用方式”

这个分代很重要，因为它决定了前期不应该被哪些问题拖住。

---

## 7. 前期工作原则

前期工作最容易犯的错误有三个：

- 过早追求复杂结构
- 过早追求自动化策略学习
- 过早追求生产级系统完整性

建议坚持下面几条原则：

### 原则 1：先保真，再压缩

先保证原始经验层完整，再谈摘要、图谱和重组。

### 原则 2：先闭环，再优化

先让“记录-检索-工作视图-反思-离线整理-写回”闭环跑起来，再谈高级策略。

### 原则 3：先定义对象和原语，再写大量业务逻辑

如果对象模型和原语语义不清楚，后面代码会很快失控。

### 原则 4：先做可验证实验，再做大而全功能

MIND 本质上是研究系统，必须从一开始就考虑如何验证。

### 原则 5：先限制范围，避免退化成泛化知识库项目

第一版只需要支撑“单 Agent 的连续多任务记忆闭环”。

### 原则 6：先区分在线记忆和离线记忆加工

不要把所有事情都塞进单次任务调用里。

工作记忆、在线检索、离线 replay、语义化沉淀，本来就应该是不同阶段的事。

---

## 8. 分阶段攻关路线

下面这部分是这份文档最重要的内容。

每个阶段都给出：

- 必要性：为什么这个阶段必须先做
- 重点：这个阶段最应该产出什么
- 难点：最可能卡住的地方
- 预计精力：粗略投入量级

说明：

- 本文保留“为什么这样分阶段”的叙述
- 每个阶段是否真的完成、能否进入下一阶段，以 [phase_gates.md](../foundation/phase_gates.md) 中的量化 gate 为准
- `phase gate` 的规则是：每条指标都必须通过；所有指标一起构成进入下一阶段的充分条件

## 8.1 阶段总览表

| 阶段 | 要解决的核心问题 | 最关键产出 | 预计精力 |
| --- | --- | --- | --- |
| A | 系统到底要怎么定义 | `SPEC`、对象模型、原语语义、utility objective | `1 ~ 1.5 人周` |
| B | 记忆底座怎么搭 | 原始记录、派生对象、关系与追踪 | `1.5 ~ 2 人周` |
| C | Agent 怎么真正操作记忆 | 最小 primitive API | `1 ~ 1.5 人周` |
| D | 当前任务怎么低成本用记忆 | 多路检索 + `workspace view` | `2 ~ 2.5 人周` |
| E | 记忆怎么变得更会记 | 反思、replay、离线整理、轻量重组 | `2 ~ 3 人周` |
| F | 如何证明这套东西值得做 | baseline、任务集、ablation、评测 | `2 ~ 3 人周` |
| G | 记忆策略如何继续优化 | 基于反馈的策略改进 | `3 ~ 6 人周` |

## 阶段 A：把系统定义说清楚

### 必要性

这是所有后续工作的基础。

如果不先把系统边界、对象模型、原语语义和优化目标讲清楚，后面实现时很容易出现三种问题：

- 原语越来越多，系统失控
- 数据结构越来越碎，无法演化
- 评估目标不统一，最后不知道系统是否真的变强

### 重点

这个阶段需要产出一版正式 spec，至少明确：

- 什么是 memory world
- 什么是 memory object
- 什么是 primitive
- 什么是 workspace view
- 什么是 memory utility objective
- 什么是 online loop 与 offline loop
- 什么是 episodic / semantic / procedural / salience 这几类对象

当前正式规范文档见 [spec.md](../foundation/spec.md)。

### 难点

- 原语最小集合怎么定
- 哪些操作允许不可逆
- 工作视图和长期表示层如何分开
- “效用”如何既体现收益又体现成本
- 认知启发应该借鉴到什么程度，哪些只是启发、哪些要真的落地

### 预计精力

- `1 ~ 1.5 人周`

### 完成标志

- 能写出一版系统说明文档
- 能把一个真实任务 episode 映射成“状态-动作-观测-反馈”

## 阶段 B：搭最小记忆内核

### 必要性

MIND 的根基不是检索，而是“可追溯、可回放、可重组”的记忆底座。

没有这个内核，后面所有反思、重组和评估都会变成漂浮逻辑。

### 重点

这个阶段先做最小数据模型和持久化能力：

- 原始记录存储
- 派生对象存储
- 关系存储
- 版本 / 来源追踪
- 记忆强度 / 显著性 / 使用次数等基础字段

建议优先支持 append-only 和 source trace。

### 难点

- 对象粒度定得太细会很碎，太粗会失去操作空间
- 派生对象如何追溯到原始数据
- 重组之后如何保留可解释性
- 如何从一开始就为后续 replay 和遗忘控制留下接口

### 预计精力

- `1.5 ~ 2 人周`

### 完成标志

- 一次完整任务轨迹可被记录和回放
- 任意摘要或反思都能追溯到原始记录

## 阶段 C：做出可用的原语接口

### 必要性

如果没有统一原语接口，Agent 无法真正“操作记忆”，项目就会退化成“外面套了几个函数的数据库”。

### 重点

建议先做一组最小但够用的原语：

- `write_raw`
- `read`
- `retrieve`
- `summarize`
- `link`
- `reflect`
- `reorganize_simple`

这个阶段重点不是原语数量，而是动作语义和返回结构要稳定。

### 难点

- 原语应该返回“对象”还是“片段”
- 原语如何带预算约束
- 删除、归档、降权等动作如何避免破坏可追溯性

### 预计精力

- `1 ~ 1.5 人周`

### 完成标志

- Agent 可以通过统一接口完成最小读写与写回操作
- 原语调用日志可被记录并分析

## 阶段 D：让系统真正“能用”而不是只“能存”

### 必要性

很多 memory 系统都停在“把信息存进去”。

MIND 必须更进一步，解决“当前任务到底怎么以合理成本拿到有用记忆”。

### 重点

这个阶段要实现两件事：

1. 多路检索
2. 有槽位限制的工作视图构建

建议最小支持：

- 关键词检索
- 向量相似检索
- 时间窗检索

然后把结果组织成 `workspace view`，而不是简单把片段拼给模型。

这里建议显式限制“快速索引句柄数”，而不是让 view builder 无限制堆上下文。

### 难点

- 工作视图该包含哪些字段
- 如何控制 token 成本
- 如何避免只偏向最近内容
- 如何平衡“原始材料”和“摘要材料”
- 槽位有限时，哪些信息应该进入工作记忆索引

### 预计精力

- `2 ~ 2.5 人周`

### 完成标志

- 连续任务中可以稳定生成可用工作视图
- 相比直接拼 raw records，有明显的成本或效果收益

## 阶段 E：补上反思、离线整理与轻量重组

### 必要性

没有这一阶段，MIND 只是“会积累”的系统，不是“会成长”的系统。

反思和重组是 MIND 与普通 memory 系统分野最大的地方之一。

### 重点

前期不追求复杂重构算法，先做轻量版本：

- 任务后反思写回
- 离线 replay 调度
- 对高价值内容生成摘要或标签
- 建立关键链接
- 可验证的跨 episode `schema synthesis`
- 对冗余或低价值结构做归档 / 降权

### 难点

- 怎么判断一条反思是有帮助的，不是噪声
- 怎么识别坏摘要、坏链接、坏结构
- 如何避免表示层不断自我污染
- replay 应优先处理弱记忆、近期记忆，还是高奖励记忆
- schema synthesis 如何避免产生漂亮但无用的伪结构

### 预计精力

- `2 ~ 3 人周`

### 完成标志

- 后续任务中可以观察到一部分记忆被复用
- 结构调整开始对成本或效果产生正向影响
- 有无离线整理时，能观察到可比较差异

## 阶段 F：建立评测与 baseline

### 必要性

如果没有 baseline，MIND 的复杂度是否值得，根本无法判断。

这个阶段的意义，是把“想法正确”变成“证据支持”。

### 重点

至少建立三类 baseline：

- no-memory
- plain RAG
- fixed summary memory

同时建立最小长程任务集，并统计：

- 成功率
- 关键事实命中率
- 平均上下文成本
- 后续任务复用率
- 有无 offline maintenance / replay 的差异

### 难点

- 什么任务才算真正测到“长期成长”
- 如何定义可比较的成本模型
- 如何把“记忆效用”量化成稳定指标
- 如何设计 ablation，证明这些认知启发不是装饰性的

### 预计精力

- `2 ~ 3 人周`

### 完成标志

- 至少在一个连续任务集上能比较 MIND 与 baseline
- 能清楚看出 MIND 的收益和代价

## 阶段 G：做策略优化

### 必要性

这是 MIND 的中后期阶段，不是前期起点。

只有前面的闭环、对象、原语、评测都站住了，这一步才有意义。

### 重点

策略优化可以从轻到重演化：

- 规则策略
- LLM 提议 + 系统约束执行
- 基于日志的离线改进
- 更进一步的 test-time optimization 或 RL 化

### 难点

- 长期 credit assignment 很难
- 策略变化到底作用在检索、写回还是重组上，需要拆清楚
- 如果前面指标不稳定，这一阶段会变成盲调

### 预计精力

- `3 ~ 6 人周`

### 完成标志

- 在相同预算下，优化后的策略优于固定规则策略

---

## 9. 早期最值得优先解决的 4 个问题

如果资源有限，优先级建议如下：

### 1. 记忆对象模型

先把“系统里到底有哪些对象”说清楚。

建议前期只保留最少对象类型：

- `RawRecord`
- `TaskEpisode`
- `SummaryNote`
- `ReflectionNote`
- `EntityNode`
- `LinkEdge`
- `WorkspaceView`
- `SchemaNote`

### 2. 原语语义

先把最少原语跑通，不追求复杂。

### 3. Workspace View

这是前期最容易被忽略、但其实非常关键的部分。

如果没有工作视图层，系统就只能“把记忆找出来”，却不能“把记忆组织成当前任务能直接用的结构”。

### 4. Utility Objective

必须尽早定义“什么叫更好的记忆”。

否则系统很容易只会：

- 记得更多
- 写得更多
- 存得更复杂

但不一定更有效。

---

## 10. 前期不要做什么

为了保证推进速度，建议前期明确不做下面这些事：

- 不先做多智能体共享记忆
- 不先做复杂图数据库方案
- 不先做非常细的权限系统
- 不先做复杂遗忘机制
- 不先做策略学习或强化学习
- 不先做过于泛化的知识平台
- 不先做“全脑模拟”式仿生系统

这些方向都可能有价值，但不是证明 MIND 核心命题成立所必需的第一步。

---

## 11. 建议的前 4 周推进方式

如果现在就开始前期工作，建议按下面这条节奏推进。

| 周次 | 主目标 | 关键产出 |
| --- | --- | --- |
| 第 1 周 | 说清系统定义 | `SPEC.md`、对象 schema、原语草案 |
| 第 2 周 | 搭记忆内核 | 最小数据模型、持久化层、episode 日志 |
| 第 3 周 | 打通检索和工作视图 | 检索器、view builder、demo episode |
| 第 4 周 | 加入反思、离线整理和最小评测 | `offline maintenance v0`、评测脚本、第一轮实验记录 |

## 第 1 周：写清楚系统定义

目标：

- 定义对象模型
- 定义原语
- 定义 workspace view
- 定义 utility objective
- 定义 online / offline 两条循环

产出：

- 一版 `SPEC.md`
- 一版对象 schema 草案
- 一版原语接口草案

## 第 2 周：搭记忆内核

目标：

- 原始记录可写入
- 派生对象可写入
- 来源与版本可追踪
- 显著性和使用强度字段可记录

产出：

- 最小数据模型
- 最小持久化层
- episode 日志格式

## 第 3 周：打通检索和工作视图

目标：

- 跑通多路检索
- 构建 workspace view
- 让 Agent 能基于该视图完成任务
- 显式限制工作记忆句柄数

产出：

- 检索器
- view builder
- demo episode

## 第 4 周：加入反思写回、离线整理和最小评测

目标：

- 跑通任务后反思
- 把反思写回表示层
- 跑通最小 replay / maintenance
- 与简单 baseline 做第一次对比

产出：

- reflect / reorganize_simple
- offline maintenance v0
- 初版评测脚本
- 第一轮实验记录

如果这 4 周做完，MIND 就已经从概念进入了“可以持续迭代的原型阶段”。

---

## 12. 最后给项目一个清晰主线

前期推进时，建议始终围绕这一条主线判断工作是否偏航：

`保留原始经验 -> 在有限工作记忆里组织快速索引 -> 生成可塑表示 -> 在任务后写回反思 -> 在离线阶段 replay / reconsolidate / promote -> 对记忆结构做归档与遗忘控制 -> 用后续任务验证是否真的更有用`

只要这条主线始终成立，项目就在朝 MIND 的核心目标前进。

如果某项工作不能明显增强这条链路，大概率就不是前期最该做的事。

---

## 13. 相关研究与可直接转化的设计结论

这一节只保留那些对 MIND 架构有直接指导意义的研究。

删掉了两类不再作为主线依据的材料：

- 过强的拟人化类比，例如“梦模块”“睡眠人格化”
- 以疾病表型直接指导系统结构的类比

### 13.1 有限工作集与 gating

- Nelson Cowan, 2001, *The magical number 4 in short-term memory*  
  链接：https://pubmed.ncbi.nlm.nih.gov/11515286/  
  可转化结论：可稳定操作的工作记忆单位是少量 chunk，而不是无限原始内容。MIND 应把 `workspace view` 设计成有限槽位句柄集合。

- Zhijian Chen, Nelson Cowan, 2009, *Core verbal working-memory capacity*  
  链接：https://pmc.ncbi.nlm.nih.gov/articles/PMC2693080/  
  可转化结论：真正可直接操作的 verbal working memory 单位更少，说明“能访问的信息总量”和“能同时操作的索引数”不是一回事。

- Fiona McNab, Torkel Klingberg, 2008, *Prefrontal cortex and basal ganglia control access to working memory*  
  链接：https://www.nature.com/articles/nn2024  
  可转化结论：工作记忆的关键不只是容量，还包括 gating。MIND 需要明确的 slot selection / filtering 机制。

### 13.2 快速情景记忆、慢速语义沉淀、以及 separation / completion

- James L. McClelland, Bruce L. McNaughton, Randall C. O'Reilly, 1995, *Why there are complementary learning systems in the hippocampus and neocortex*  
  链接：https://pubmed.ncbi.nlm.nih.gov/7624455/  
  可转化结论：快速 episodic 学习和慢速结构化泛化最好由互补系统承担。MIND 不应只有一个统一记忆层。

- Randall C. O'Reilly, Kenneth A. Norman, 2002, *Hippocampal and neocortical contributions to memory*  
  链接：https://pubmed.ncbi.nlm.nih.gov/12475710/  
  可转化结论：新经验需要快速编码，但长期结构需要慢速整合。MIND 的 episodic 层和 semantic 层应有不同职责。

- Michael A. Yassa, Craig E. L. Stark, 2011, *Pattern separation in the hippocampus*  
  链接：https://pubmed.ncbi.nlm.nih.gov/21788086/  
  可转化结论：存储相似经历时，需要强调 separation，避免过早混淆。MIND 的 episodic 层应保留差异。

- Edmund T. Rolls, 2013, *The mechanisms for pattern completion and pattern separation in the hippocampus*  
  链接：https://pmc.ncbi.nlm.nih.gov/articles/PMC3812781/  
  可转化结论：回忆阶段允许依据部分线索做 completion。MIND 在 retrieval 阶段可以允许稀疏线索补全，但不能在写入时过早合并。

### 13.3 离线 replay 与 priority replay

- Björn Rasch et al., 2007, *Odor cues during slow-wave sleep prompt declarative memory consolidation*  
  链接：https://pubmed.ncbi.nlm.nih.gov/17347444/  
  可转化结论：记忆强化不只发生在在线任务中。MIND 应有独立的 `offline maintenance loop`。

- Anna C. Schapiro et al., 2018, *Human hippocampal replay during rest prioritizes weakly learned information and predicts memory performance*  
  链接：https://pmc.ncbi.nlm.nih.gov/articles/PMC6156217/  
  可转化结论：replay 不是平均分配，弱记忆会被优先重放。MIND 的 replay 应该是 priority replay，而不是全量回放。

- Marta Huelin Gorriz et al., 2023, *The role of experience in prioritizing hippocampal replay*  
  链接：https://www.nature.com/articles/s41467-023-43939-z  
  可转化结论：显著性、更新度和经验暴露会影响 replay 优先级。MIND 需要 `priority / novelty / exposure` 字段。

### 13.4 Reconsolidation 与 promotion

- Karim Nader, Oliver Hardt, 2009, *A single standard for memory: the case for reconsolidation*  
  链接：https://pubmed.ncbi.nlm.nih.gov/19229241/  
  可转化结论：被重新激活的记忆会重新进入可塑状态。MIND 中，被取回并修订的对象应生成新版本，而不是原地覆盖。

说明：

- `promotion policy` 是在上述研究基础上的工程抽象，不是直接照搬某一条生物机制
- 它对应的问题是：什么样的 episodic 经验值得晋升为 semantic schema 或 procedural policy

### 13.5 主动遗忘与抑制

- Jacob A. Berry et al., 2012, *Dopamine Is Required for Learning and Forgetting in Drosophila*  
  链接：https://pmc.ncbi.nlm.nih.gov/articles/PMC4083655/  
  可转化结论：遗忘可以是主动调节过程，而不只是被动衰减。MIND 应把 forgetting 实现成策略能力，包括降权、抑制、归档和可恢复删除。
