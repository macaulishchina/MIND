# MIND Growth Architecture — Counter-Proposal

> **团队 B 对 Growth Architecture Plan 的独立评审与替代方案**

本文档基于对 MIND 当前代码库（Phase J baseline）和原始设计文档（README.md、design_breakdown.md）的完整审计，从另一个视角给出评审意见和替代方案。

---

## 〇、审查方法论

我们的审查遵循三条原则：

1. **以代码为锚**：所有判断都回到 MIND 当前实现状态，而不是在设计文档的空气中对话
2. **以落地代价为尺**：所有建议都附带对"改多少代码、引入多少风险、需要几个人多少时间"的粗略估算
3. **以成长闭环为纲**：MIND 的核心命题是"记忆演化闭环"，任何不服务于这个闭环的优化都应后排

---

## 一、对原方案的总体评价

### 1.1 原方案做对了什么

原方案对 MIND 设计哲学的理解是准确的。以下几点我们完全认同：

- MIND 不等于 RAG，必须包含写回、反思、重组、晋升
- LLM 应参与高杠杆节点，不应无处不在
- online / offline / governance 三循环必须隔离
- 工作记忆必须是有限句柄集合
- 统一目标是"成本受限条件下的未来任务效用最大化"

这些不是空话——MIND 当前代码库确实已经在实践这些原则（7 个 primitive、4 档 access mode、offline worker、governance control plane）。

### 1.2 原方案的系统性问题

但原方案存在三个结构性缺陷：

**问题 A：建议密度过高，缺乏依赖关系图**

原方案列出了 ~30 条建议，按 P0/P1/P2 做了粗略分级，但没有画出它们之间的依赖关系。例如：

- "Ingest Triage"（输入 P0-1）和"双通道输入"（输入 P0-2）有强依赖，但被当作独立条目
- "Memory Planner"（输出 P0-1）依赖于"多层记忆存储"（存储 P0-1），但后者被排在第二优先级
- "Hybrid Retrieval"（输出 P0-2）依赖于"更强的表征层"（存储 P1-3），但表征层优先级更低

没有依赖图，执行团队会在依赖链中间卡住。

**问题 B：大量建议和现有实现重叠，但未标注**

原方案未充分审计 MIND 当前代码库。以下建议在当前实现中已有对应物：

| 原方案建议 | MIND 当前实现 |
|---|---|
| 输入 P0-2 双通道 Raw+Structured | `write_raw` + `summarize`/`reflect`/`link` 已形成双通道 |
| 存储 P0-3 Proposal→Verify→Commit | `assess_schema_promotion()` + evidence check 已存在 |
| 输出 P0-1 Memory Planner | 4 档 `_ModePlan` + `auto` 调度器已实现 |
| 存储 P1-1 Reconsolidation | 版本链 `versions_for_object()` 已支持 |
| 输出 P1-1 强化 Workspace Selection | `WorkspaceBuilder` 已有 slot 限制和优先级选择 |
| 跨阶段建议 3: 对象级 trace | `DirectProvenanceRecord` + `GovernanceAuditRecord` 已有 |

不标注重叠，会让执行团队重复建设已有功能，浪费资源。

**问题 C：缺乏对"当前最短板"的诊断**

原方案按"输入→存储→输出"线性铺开，但没有回答最关键的问题：**MIND 当前闭环中最弱的一环是什么？**

基于代码审计，我们认为当前最弱的 3 个环节是：

1. **检索质量**：当前检索基于 `pg_trgm` + deterministic embedding，没有真正的 dense retrieval
2. **离线维护触发策略**：当前 `select_replay_targets` 是简单优先级排序，无自适应调度
3. **没有闭环反馈信号**：查询后没有把"这次回答用了哪些记忆、哪些有帮助"写回优先级

原方案在"输入分流器""多层记忆系统"等方向投入大量笔墨，但这些不是当前瓶颈。

---

## 二、我们的替代方案

### 核心思路：先补最短板，再扩新能力

我们把后续工作分为三个阶段：

- **Phase α：补完闭环**（1-2 个月）—— 把当前断裂的反馈环路接上
- **Phase β：提升核心质量**（2-3 个月）—— 升级检索、离线调度和工作记忆选择
- **Phase γ：扩展能力边界**（3-6 个月）—— 新记忆类型、新检索方式、新对象生命周期

---

## Phase α：补完闭环（先做，1-2 月）

### α-1 查询后反馈写回（Post-Query Feedback Loop）

**现状诊断：**

当前 `AccessService.run()` 执行完后返回 `AccessRunResponse`，包含 trace 和候选信息。但这些信息**没有被写回任何持久化的 feedback 信号**。`access` 层和 `offline` 层之间没有闭环。

**具体方案：**

1. 在 `AccessRunResponse` 中增加 `used_object_ids` 和 `answer_quality_signal`（由调用方或自评提供）
2. 新增 primitive `record_feedback`，将 feedback 写入一个新的 `FeedbackRecord` 对象类型
3. `FeedbackRecord` 字段：`task_id, episode_id, query, used_object_ids, helpful_object_ids, unhelpful_object_ids, quality_signal, cost`
4. Offline worker 消费 `FeedbackRecord` 来更新对象优先级

**改动范围：**

- 修改 `mind/access/contracts.py`：扩展 response
- 新增 `FeedbackRecord` 到 `CORE_OBJECT_TYPES`（或作为独立 metadata 表）
- 新增 `record_feedback` primitive 或 app service endpoint
- 修改 `mind/offline/replay.py`：`_replay_score()` 消费 feedback
- 新增 1 张 Alembic migration

**风险：** 低。只是在现有循环上加了一条边。

**估算：** 1 人 1-2 周

### α-2 对象优先级动态更新（Priority Signal Evolution）

**现状诊断：**

当前对象有 `priority` 字段（0-100），但它在写入后是**静态的**。`select_replay_targets` 读取了 priority 但无法根据使用情况调整。

**具体方案：**

1. 为每个对象维护一组动态信号字段，放在 `metadata` 中或独立表中：
   - `access_count`：被检索命中次数
   - `feedback_positive_count`：被标记为有帮助的次数
   - `feedback_negative_count`：被标记为无帮助的次数
   - `last_accessed_at`：最后被访问时间
   - `decay_score`：时间衰减值
2. `_replay_score()` 改为综合公式：`f(priority, access_count, feedback_signal, recency, fragility)`
3. 新增 offline job kind `UPDATE_PRIORITY`，定期批量刷新对象的综合评分

**改动范围：**

- 修改 `mind/kernel/schema.py`：metadata 新增可选字段
- 修改 `mind/offline/replay.py`：升级评分函数
- 新增 `OfflineJobKind.UPDATE_PRIORITY`
- 修改 `mind/offline/service.py`：处理新 job kind

**风险：** 低。不改变现有数据模型结构，只扩展 metadata。

**估算：** 1 人 1 周

### α-3 Offline Worker 自触发机制

**现状诊断：**

当前 offline worker 需要外部手动触发 (`run_once`)。没有自动 job 提交逻辑——即谁负责**创建** `reflect_episode` 和 `promote_schema` 的 job？

**具体方案：**

1. 新增 `OfflineJobScheduler` 组件，挂在 `write_raw` 或 episode 完成事件之后
2. 当一个 episode 结束时（由 `TaskEpisode` 的 `result` 字段从空变非空触发），自动 enqueue `REFLECT_EPISODE`
3. 当 `FeedbackRecord` 中某对象被正向反馈超过 N 次，自动 enqueue `PROMOTE_SCHEMA` 候选
4. 在 API/MCP 层暴露 `POST /jobs/enqueue` 端点，允许外部系统也能触发

**改动范围：**

- 新增 `mind/offline/scheduler.py`
- 修改 `mind/app/services/` 中的内存操作链路，在适当位置插入 scheduler 调用
- 修改 `mind/api/routers/jobs.py`：新增 enqueue 端点

**风险：** 中。需要小心控制自动触发频率，避免 job 风暴。

**估算：** 1 人 1-2 周

### α-4 最小闭环评测指标

**现状诊断：**

当前 eval 侧有 `LongHorizonEval` 和 `EpisodeAnswerBench`，但**缺少对"闭环成长性"的直接度量**。即：离线维护之后，后续任务的表现是否真的变好了？

**具体方案：**

1. 新增 eval 指标 `GrowthLift`：对比"有离线维护的连续任务序列"和"无离线维护的连续任务序列"之间的 answer quality 差异
2. 新增 eval 指标 `MemoryEfficiency`：`(quality * task_count) / total_objects`，衡量记忆系统是否在"用更少记忆做更多事"
3. 新增 eval 指标 `FeedbackCorrelation`：positive feedback 对象的后续复用率 vs negative feedback 对象的后续复用率

**改动范围：**

- 扩展 `mind/eval/` 新增 metrics
- 扩展现有 `LongHorizonEval` runner 支持 A/B 对比

**风险：** 低。纯增量。

**估算：** 1 人 1 周

---

## Phase β：提升核心质量（2-3 月）

### β-1 真正的 Dense Retrieval

**现状诊断：**

当前 `build_query_embedding` 使用的是 deterministic embedding（hash-based），`pgvector` 表虽然已建，但实际 embedding 质量有限。检索主要依赖 `pg_trgm` 的词法匹配。

**具体方案：**

1. 引入 sentence-transformer 或 API-based embedding（OpenAI / Cohere）生成高质量 dense embedding
2. 在 `object_embeddings` 表中存储真实 dense embedding
3. 检索改为 hybrid：`lexical_score * w1 + dense_score * w2 + priority_score * w3`
4. 权重 w1/w2/w3 可以作为 eval 超参数调优
5. 新增 offline job `REFRESH_EMBEDDINGS`，定期为新对象补充 embedding

**与原方案的差异：**

原方案把"Hybrid Retrieval"放在输出 P0-2，但没有给出如何从当前 deterministic embedding 迁移到 dense embedding 的具体路径。我们认为 **embedding 质量是检索质量的前提**，应在 hybrid retrieval 之前先解决。

**改动范围：**

- 新增 `mind/kernel/embedding.py`：真实 embedding 生成
- 修改 `mind/kernel/retrieval.py`：hybrid scoring
- 修改 `mind/kernel/postgres_store.py`：embedding 写入和 ANN 查询
- 新增 Alembic migration：扩展 embedding 维度
- 新增 `OfflineJobKind.REFRESH_EMBEDDINGS`

**风险：** 中。需要管理 embedding 服务的依赖和成本。

**估算：** 1 人 2-3 周

### β-2 输入冲突检测（Input Conflict Detection）

**现状诊断：**

当前 `write_raw` 是纯 append，没有任何与已有记忆的比对。同一事实的多次不一致记录会同时存在于系统中。

**具体方案：**

1. 在 `write_raw` 后增加一个**异步**冲突检测步骤（不阻塞写入路径）
2. 对新写入对象做一次 lightweight retrieval（top-3），计算与近邻的关系：
   - `similar`：可能是同一事实的重复
   - `contradictory`：与已有记忆矛盾
   - `novel`：全新信息
3. 检测结果写入对象 metadata 的 `conflict_candidates` 字段
4. 高置信度矛盾自动 enqueue `RESOLVE_CONFLICT` offline job

**与原方案的差异：**

原方案把冲突检测和"输入分流器""价值评估""新颖性评估"分成 4 个独立条目。我们认为这些本质上是**同一次 lightweight recall 的不同输出维度**，应合并实现。

**改动范围：**

- 新增 `mind/primitives/conflict.py`：冲突检测逻辑
- 修改 `write_raw` 后的异步处理链
- 新增 `OfflineJobKind.RESOLVE_CONFLICT`

**风险：** 中。需要控制异步检测的延迟和 false positive 率。

**估算：** 1 人 2 周

### β-3 Workspace 选择策略增强

**现状诊断：**

当前 `WorkspaceBuilder` 按 retrieval score 排序选入 slot。没有对"evidence diversity"（raw vs summary、supporting vs conflicting、recent vs stable）做显式平衡。

**具体方案：**

1. 在 `WorkspaceBuilder` 中引入 slot allocation policy：
   - 至少 1 个 slot 给 raw evidence（如果可用）
   - 至少 1 个 slot 给不同 episode 的对象（多样性约束）
   - 如果检测到 conflict_candidates（来自 β-2），显式纳入矛盾证据
2. Slot allocation policy 作为可配置参数，不同 AccessMode 可有不同策略
3. 在 `AccessDepthBench` 中增加对 evidence diversity 的衡量维度

**改动范围：**

- 修改 `mind/workspace/builder.py`：slot allocation logic
- 修改 `mind/access/service.py`：将 policy 传入 builder
- 扩展 `mind/access/benchmark.py`：diversity metric

**风险：** 中。多样性约束可能降低 top-hit 概率，需要 eval 验证。

**估算：** 1 人 1-2 周

### β-4 Promotion Pipeline 强化：Proposal Lifecycle

**现状诊断：**

当前 `assess_schema_promotion()` 的验证逻辑是：

- 至少 2 个 source objects
- 全部 active
- 至少来自 2 个不同 episode
- stability_score 计算基于 episode 数量

这是一个合理的起点，但缺乏反证检查（有没有矛盾证据？）和 confidence decay（旧证据是否还有效？）。

**具体方案：**

1. 为 `SchemaNote` 引入 `proposal_status` metadata 字段：`proposed | verified | committed | rejected`
2. 新增 `VERIFY_PROPOSAL` offline job kind，由 LLM 检查：
   - 是否有跨 episode 反证
   - 证据是否覆盖关键条件
   - 是否和已有 SchemaNote 冲突
3. 只有 `verified` 状态的 SchemaNote 才进入默认检索范围
4. `rejected` 的 SchemaNote 保留审计记录但不参与检索

**与原方案的差异：**

原方案描述了 Proposal→Verify→Commit 的理念，但没有说明如何与当前 `assess_schema_promotion()` 函数融合。我们的方案是在现有函数基础上**增加一个异步 verify 步骤**，而不是重写整个 promotion 流程。

**改动范围：**

- 修改 `mind/offline/promotion.py`：加入 proposal lifecycle
- 修改 `mind/offline/service.py`：新增 VERIFY_PROPOSAL job handler
- 修改检索路径：filter by `proposal_status`

**风险：** 中高。LLM 验证引入了成本和延迟。

**估算：** 1 人 2-3 周

### β-5 Auto 模式决策增强

**现状诊断：**

当前 `auto` 调度基于规则（`_plan_auto_mode`），根据 task family 和简单信号选择档位。但缺少：

- 根据检索结果质量动态升级的能力
- 根据 budget 余量降级的能力
- 根据历史同类任务表现选择档位的能力

**具体方案：**

1. 在 `auto` 模式中引入 **two-phase 策略**：
   - Phase 1：以 `Flash` 模式做一次 scouting retrieval
   - Phase 2：根据 scouting 结果的覆盖度和冲突率，决定最终档位
2. 引入 `task_type → historical_best_mode` 的轻量缓存（基于 FeedbackRecord 统计）
3. 在 budget 使用超过 80% 时自动降级

**改动范围：**

- 修改 `mind/access/service.py`：`auto` 模式决策逻辑
- 新增 `mind/access/mode_history.py`：历史档位性能缓存

**风险：** 中。two-phase 增加了一次 retrieval 调用，需要验证总体成本是否可接受。

**估算：** 1 人 2 周

---

## Phase γ：扩展能力边界（3-6 月）

### γ-1 新记忆类型：PolicyNote / PreferenceNote

**现状诊断：**

当前 `CORE_OBJECT_TYPES` 有 8 种，其中 `SchemaNote` 承载了"稳定知识"的角色。但"用户偏好"和"操作策略"没有独立类型。

**具体方案：**

1. 新增 `PolicyNote`：记录"在某种情境下应该怎么做"
   - metadata: `trigger_condition, action_pattern, evidence_refs, confidence, applies_to_scope`
2. 新增 `PreferenceNote`：记录"用户/agent 的稳定偏好"
   - metadata: `preference_key, preference_value, strength, evidence_refs, last_confirmed_at`
3. 这两种类型应该有**比 SchemaNote 更高的 promotion 门槛**（因为错误的 policy/preference 影响更大）
4. 在 Workspace 构建中，当检测到任务涉及决策或偏好时，优先纳入这两种类型

**与原方案的差异：**

原方案在"存储 P0-1"中提到了 Procedural/Policy/Value/Persona Store，但把它们描述成独立存储层。我们认为**不需要独立存储层**——PostgreSQL 已有的对象表完全够用，只需要新增对象类型和对应的 promotion policy。

**风险：** 中。新类型需要 schema migration、新的 golden fixtures、新的 gate criteria。

**估算：** 1 人 3-4 周

### γ-2 Graph-Augmented Retrieval

**现状诊断：**

当前 `LinkEdge` 对象已经存在，但检索路径中**没有使用 graph walk**。`retrieve` 只做 flat search。

**具体方案：**

1. 在 `Recall` 及以上档位中，对检索结果做 1-hop graph expand：
   - 从命中对象出发，沿 `LinkEdge` 找到关联对象
   - 将关联对象加入候选池（但优先级低于直接命中）
2. 在 `Reconstruct` 档位中支持 2-hop expand
3. 在 offline 阶段增加 `BUILD_LINK_INDEX` job，维护一个轻量的邻接表缓存

**改动范围：**

- 修改 `mind/primitives/service.py`：retrieval 后 graph expand
- 新增 `mind/kernel/graph.py`：邻接表和 walk 逻辑
- 修改 `mind/access/service.py`：在各档位计划中加入 expand 预算

**风险：** 中。graph walk 可能引入噪声，需要在 benchmark 中验证。

**估算：** 1 人 2-3 周

### γ-3 分层模型路由

**现状诊断：**

当前 `CapabilityService` 支持 OpenAI、Claude、Gemini 和 deterministic fallback，但所有 capability 请求走同一个 provider。没有"小模型做 triage、大模型做 synthesis"的分层。

**具体方案：**

1. 在 `CapabilityProviderConfig` 中支持 per-capability routing：
   - `summarize` → 小模型 / fast model
   - `reflect` → 中模型
   - `answer`（高正确性）→ 大模型
   - `offline_reconstruct` → 中/大模型
2. 引入 `ModelRoutingPolicy` 配置，可通过 CLI config 或环境变量设置
3. fallback 策略保持不变

**改动范围：**

- 修改 `mind/capabilities/contracts.py`：per-capability provider config
- 修改 `mind/capabilities/service.py`：routing 逻辑
- 修改 `mind/cli_config.py`：配置层面支持

**风险：** 中。多 provider 管理增加了运维复杂度。

**估算：** 1 人 2 周

### γ-4 Structured Artifact Memory（PageIndex 思路落地）

**现状诊断：**

当前所有对象的检索粒度是"整个对象"。对于长文档、长 episode、长代码文件来说，这要么太粗（整文档命中但多数内容不相关），要么太细（被 chunk 切碎后丢失结构）。

**具体方案：**

1. 新增 `ArtifactIndex` 对象类型，为长对象建立树状结构索引
2. 树节点包含：`section_id, parent_id, heading, summary, content_range, depth`
3. 检索时先命中 artifact 顶层，再沿树向下 drill-down
4. 只在 `Reconstruct` 及以上档位启用 artifact tree navigation
5. 初期只对 `RawRecord(record_kind=document)` 和 `TaskEpisode(长度 > 阈值)` 建索引

**风险：** 高。索引构建成本高，更新困难，需要先做试点验证。

**估算：** 1-2 人 4-6 周

### γ-5 记忆衰减与自动归档

**现状诊断：**

当前对象有 `status` 字段（active / archived / deprecated / invalid），但没有自动归档策略。所有 active 对象永远参与检索。

**具体方案：**

1. 新增 offline job `AUTO_ARCHIVE`，定期扫描并归档满足以下条件的对象：
   - `last_accessed_at > 90 天` 且 `feedback_positive_count == 0`
   - `decay_score < 阈值`（需 α-2 的动态信号支持）
   - 类型为 `RawRecord` 且已有 `SummaryNote` 覆盖
2. 归档不是删除——对象状态变为 `archived`，不参与默认检索，但可被 `Reconstruct`/`Reflective` 显式召回
3. 定期生成 `ArchiveReport`，供人工审查

**风险：** 中。误归档风险，但因为可恢复所以影响有限。

**估算：** 1 人 1-2 周

---

## 三、原方案中我们认为不应该做的事

### ❌ 不建议做：输入分流器（Ingest Triage）

**原方案位置：** 输入 P0-1

**我们的理由：**

MIND 的设计原则第一条是"原始经验优先"。在写入之前增加分流层，意味着在最早期就引入了一个**不可逆的判断节点**。如果分流器误判，高价值信号可能被错误降级。

当前 MIND 的写入路径是 `write_raw → append-only`，这个设计的简洁性和安全性非常高。我们建议**保持写入路径的纯净性**，所有分类和标注工作放在写入之后的异步路径中（这正是 β-2 冲突检测的做法）。

如果未来确实遇到高吞吐场景的写入压力，应该通过**队列化和批处理**解决，而不是通过引入分流器。

### ❌ 不建议做（近期）：多层记忆存储拆分

**原方案位置：** 存储 P0-1

**我们的理由：**

原方案建议把当前的对象表拆成 `Episodic Fast Store`、`Semantic/Schema Store`、`Procedural/Policy Store`、`Value/Persona Store` 四个物理存储。

但 MIND 当前的 PostgreSQL 存储已经通过 `object_type` 字段做了逻辑区分。物理拆分会带来：

- 跨表 join 复杂度
- 事务边界变大
- 迁移成本显著
- 检索路径需要多路合并

更实际的做法是：保持单一物理存储，通过 `object_type` 过滤和针对性索引来实现逻辑分层。`_ModePlan` 中根据 `object_types` 过滤候选，已经是这种思路。

### ❌ 不建议做（近期）：Multi-Armed Bandit / RL 优化

**原方案位置：** 第八节第 6 条

**我们的理由：**

在 feedback 信号稀疏、task 分布不稳定的早期阶段，RL/Bandit 方法缺乏足够的训练数据，很容易收敛到次优策略或不稳定振荡。

更稳妥的路径是先通过 α-1（feedback 写回）和 α-2（动态优先级）积累足够的历史数据，再在数据充分后考虑 bandit style 的策略优化。

### ❌ 不建议做（近期）：全面 LLM Verifier

**原方案位置：** LLM P1-3

**我们的理由：**

对每个 schema/policy/value memory 都做 LLM 二次校验，成本极高。MIND 当前的 SchemaNote 吞吐量还在可控范围——`assess_schema_promotion` 的规则验证已经能过滤掉大部分低质量候选。

我们建议只在 **β-4 的 VERIFY_PROPOSAL job** 中为高优先级候选做 LLM 验证，而不是全覆盖。

---

## 四、原方案完全忽略的重要方向

### ★ 方向 1：Session / Multi-Turn 上下文积累

**问题：**

当前 MIND 的 `session` 概念已经在 API 和 CLI 层出现（`sessions_router`），但每次 access run 是**独立的**——没有把同一 session 内的多轮对话结果累积起来影响后续轮次的检索和 workspace 构建。

**为什么重要：**

在实际产品交互中，用户的问题序列是有连续性的。如果第 3 轮对话可以利用第 1、2 轮的检索结果、反馈信号和上下文，整体体验和质量会显著提升。

**建议：**

1. 在 `AccessRunRequest` 中引入 `session_context`，包含本 session 内之前轮次的 summary、used objects 和 feedback
2. Workspace 构建时将 session context 作为额外 slot 纳入
3. 这比从头做一套"Memory Planner"简单得多，但效果可能更直接

### ★ 方向 2：记忆系统的可解释性输出

**问题：**

当前 `AccessRunResponse` 包含 `trace` 信息，但这只是内部调试用途。用户看到的回答**没有附带"这个回答基于哪些记忆"的可见解释**。

**为什么重要：**

记忆系统的信任度取决于用户能否知道"系统为什么记得这件事"和"系统为什么不记得那件事"。这不仅是产品体验问题，也是 governance 的前提——用户需要知道哪些记忆在影响系统行为，才能决定是否需要 conceal 或 reshape。

**建议：**

1. 在回答中附带 `evidence_summary`：列出 top-3 最相关的记忆对象 id 和简短描述
2. 前端展示 evidence provenance chain
3. 这和原方案提到的"对象级 trace"是互补的，但方向不同——trace 面向开发者，evidence_summary 面向用户

### ★ 方向 3：跨 Episode 关联的自动发现

**问题：**

当前 `LinkEdge` 需要通过 `link` primitive 显式创建。没有自动发现跨 episode 关联的机制。

**为什么重要：**

记忆成长的一个关键标志是"系统能自己发现以前不知道的关联"。如果所有 link 都要人工或显式触发，link graph 会很稀疏。

**建议：**

1. 新增 offline job `DISCOVER_LINKS`：对高优先级对象做 embedding 近邻搜索，找到跨 episode 的相似对象
2. 对相似度超过阈值的对象对，自动创建 `proposed` 状态的 LinkEdge
3. 这些 proposed link 在被 retrieve 命中并使用后，如果获得正面 feedback，自动升级为 `active`

### ★ 方向 4：记忆系统的容量治理与健康度监控

**问题：**

原方案大量讨论了如何让记忆变好，但没有讨论如何知道"记忆系统当前的状态是否健康"。

**为什么重要：**

一个没有健康监控的记忆系统，迟早会出现：对象数量失控、embedding 维度不一致、orphan objects（有引用但对象已不存在）、promotion pipeline 堵塞等问题。

**建议：**

1. 新增 `mindtest health` / `mind status --detailed` 命令，输出：
   - 各类型对象数量和状态分布
   - 平均 priority 分布
   - 最近 N 天的 feedback positive/negative ratio
   - orphan reference 数量
   - pending offline job 队列深度
   - embedding coverage ratio（有 embedding 的对象占比）
2. 新增 `HealthCheck` 定期 job，将结果写入 telemetry

---

## 五、总排序：我们的优先级矩阵

### 第一优先级（先做）—— 补完闭环

| ID | 建议 | 估算 | 风险 | 依赖 |
|---|---|---|---|---|
| α-1 | 查询后反馈写回 | 1-2 周 | 低 | 无 |
| α-2 | 对象优先级动态更新 | 1 周 | 低 | α-1 |
| α-3 | Offline Worker 自触发 | 1-2 周 | 中 | 无 |
| α-4 | 闭环成长性评测指标 | 1 周 | 低 | α-1 |

### 第二优先级（随后做）—— 提升核心质量

| ID | 建议 | 估算 | 风险 | 依赖 |
|---|---|---|---|---|
| β-1 | Dense Retrieval | 2-3 周 | 中 | 无 |
| β-2 | 输入冲突检测 | 2 周 | 中 | β-1（需要 embedding） |
| β-3 | Workspace 选择策略增强 | 1-2 周 | 中 | β-2（conflict 信号） |
| β-4 | Promotion Pipeline + Proposal Lifecycle | 2-3 周 | 中高 | α-3（job 调度） |
| β-5 | Auto 模式决策增强 | 2 周 | 中 | α-1, α-2 |

### 第三优先级（在闭环稳定后做）—— 扩展能力

| ID | 建议 | 估算 | 风险 | 依赖 |
|---|---|---|---|---|
| γ-1 | PolicyNote / PreferenceNote | 3-4 周 | 中 | β-4 |
| γ-2 | Graph-Augmented Retrieval | 2-3 周 | 中 | β-1 |
| γ-3 | 分层模型路由 | 2 周 | 中 | 无 |
| γ-4 | Structured Artifact Memory | 4-6 周 | 高 | β-1 |
| γ-5 | 记忆衰减与自动归档 | 1-2 周 | 中 | α-2 |

### 应尽早穿插的增量改进

| 建议 | 估算 | 可与哪个阶段并行 |
|---|---|---|
| Session 上下文积累 | 1-2 周 | α |
| 记忆可解释性输出 | 1 周 | α |
| 跨 Episode 自动 Link 发现 | 2 周 | β |
| 系统健康度监控 | 1-2 周 | α |

---

## 六、依赖关系图

```
α-1 (Feedback) ──→ α-2 (Priority) ──→ β-5 (Auto Mode)
     │                    │                    ↑
     │                    └──→ γ-5 (Decay)     │
     └──→ α-4 (Eval)                          │
                                               │
α-3 (Scheduler) ──→ β-4 (Promotion) ──→ γ-1 (New Types)
                                               │
β-1 (Dense Emb) ──→ β-2 (Conflict) ──→ β-3 (Workspace)
     │                                         
     ├──→ γ-2 (Graph Retrieval)                
     └──→ γ-4 (Artifact Memory)                
                                               
γ-3 (Model Routing) ── 独立，可随时启动
```

---

## 七、最关键的结论

### 与原方案的 3 点根本分歧

1. **先闭环，后扩展**。原方案想在输入、存储、输出三个方向同时推进 P0 改进，总共 6 个 P0。我们认为当前最缺的是**feedback 闭环**——没有反馈信号，任何检索升级和离线优化都是盲目的。

2. **保持写入路径纯净**。原方案想在写入前加分流器、同步做冲突检测和价值评估。我们认为写入路径应保持 append-only 的简洁性，所有分析放在异步路径中。这是 MIND "原始经验优先"原则的直接推论。

3. **不拆物理存储层**。原方案建议把记忆分成 4 个独立 store。我们认为当前 PostgreSQL + `object_type` 过滤已经足够，物理拆分的工程代价远大于收益。

### 我们方案的一句话总结

> **MIND 当前不缺建议，缺的是从"能存能查"到"存了之后知道哪些有用、无用的自动淘汰"的最后一公里闭环。补上这条闭环，后面的一切优化才有方向。**
