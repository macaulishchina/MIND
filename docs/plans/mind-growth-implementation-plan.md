# MIND Growth — 详细实现计划表

> **基于 Counter-Proposal 的可执行工程计划**
>
> 按阶段 × 优先级排列。每个任务附带：要改的文件、新增的文件、验收标准、依赖项和估算。

---

## 全局约定

| 约定 | 说明 |
|---|---|
| 分支策略 | 每个 α/β/γ 编号一个 feature branch，如 `feat/alpha-1-feedback-loop` |
| 测试红线 | 每个任务完成后 `uv run pytest -q` 全绿，`uv run ruff check mind tests scripts` 零警告，`uv run mypy` 零错误 |
| Gate 兼容 | 已有 Phase B~J gate 不得因新代码退化（CI 跑全套 gate） |
| Migration 命名 | `YYYYMMDD_NNNN_short_description.py`，编号紧接当前 `20260312_0009` |
| 对象模型变更 | 改 `mind/kernel/schema.py` 的同时必须更新 `mind/fixtures/golden_episode_set.py` 中对应样例 |
| 新 offline job kind | 加入 `OfflineJobKind` 枚举 + payload model + `OfflineMaintenanceService.process_job` handler + 测试 |

---

## Phase α：补完闭环（第 1-2 月）

---

### α-1 查询后反馈写回（Post-Query Feedback Loop）

**目标**：让 access 层的结果能回流到 offline 层，形成"用→反馈→优化"闭环。

#### 任务分解

| 序号 | 子任务 | 要改的文件 | 新增的文件 | 说明 |
|---|---|---|---|---|
| α-1.1 | 定义 `FeedbackRecord` schema | `mind/kernel/schema.py` | — | 在 `CORE_OBJECT_TYPES` 中新增 `"FeedbackRecord"`；在 `REQUIRED_METADATA_FIELDS` 中新增 `"FeedbackRecord": ("task_id", "episode_id", "query_hash", "used_object_ids", "helpful_object_ids", "unhelpful_object_ids", "quality_signal")`。字段说明见下表。 |
| α-1.2 | 新增 `record_feedback` primitive contract | `mind/primitives/contracts.py` | — | 新增 `RecordFeedbackRequest` / `RecordFeedbackResponse` Pydantic model。`PrimitiveName` 枚举新增 `RECORD_FEEDBACK = "record_feedback"`。 |
| α-1.3 | 实现 `record_feedback` primitive service | `mind/primitives/service.py` | — | 在 `PrimitiveService` 中新增 `record_feedback()` 方法。逻辑：验证 `used_object_ids` 都存在 → 构造 `FeedbackRecord` 对象 → `store.insert_object()` → 返回 response。事务内执行，失败原子回滚。 |
| α-1.4 | 扩展 `AccessRunResponse` 增加反馈字段 | `mind/access/contracts.py` | — | 在 `AccessRunResponse` 中增加可选字段：`feedback_hint: dict[str, Any] \| None = None`。该字段由调用方回传，用于下游自动或手动反馈。 |
| α-1.5 | App service：feedback 端点 | `mind/app/services/ingest.py` 或新增 `mind/app/services/feedback.py` | 若新增文件则同时新增 `mind/api/routers/feedback.py` | 暴露 `POST /memories/feedback` 接口。请求体：`{ task_id, episode_id, query, used_object_ids, helpful_object_ids, unhelpful_object_ids, quality_signal }`。调 `PrimitiveService.record_feedback()`。 |
| α-1.6 | MCP 端点 | `mind/mcp/server.py` | — | 新增 tool `"record_feedback"`，调 `registry.memory_ingest_service` 或新建的 feedback app service。 |
| α-1.7 | CLI 命令 | `mind/product_cli.py` | — | 新增 `mind feedback` 子命令（最简版：`mind feedback --task-id ... --helpful ... --unhelpful ...`）。 |
| α-1.8 | DB migration | — | `alembic/versions/20260313_0010_feedback_record.py` | 如果 FeedbackRecord 走 `object_versions` 表则无需独立表；如果作为独立表则需 migration。**推荐**：复用 `object_versions` 表，`type="FeedbackRecord"`，不需要独立 migration。 |
| α-1.9 | Golden fixtures | `mind/fixtures/golden_episode_set.py` | — | 新增 2-3 个 `FeedbackRecord` 样例。 |
| α-1.10 | 测试 | — | `tests/test_feedback_loop.py` | 覆盖：record_feedback 成功/失败、对象引用不存在时报错、feedback 对象可被 read/retrieve。 |

#### FeedbackRecord metadata 字段说明

| 字段 | 类型 | 说明 |
|---|---|---|
| `task_id` | `str` | 对应的任务 ID |
| `episode_id` | `str` | 对应的 episode ID |
| `query_hash` | `str` | 查询内容的 SHA256 前 16 字符，用于去重和关联 |
| `used_object_ids` | `list[str]` | 本次查询中被访问的对象 ID 列表 |
| `helpful_object_ids` | `list[str]` | 用户或自评标记为有帮助的对象 |
| `unhelpful_object_ids` | `list[str]` | 用户或自评标记为无帮助的对象 |
| `quality_signal` | `float` | 0.0~1.0，本次回答的整体质量评分 |

#### 验收标准

- [ ] `uv run pytest tests/test_feedback_loop.py -q` 全绿
- [ ] `uv run mindtest primitive record-feedback --help` 可用
- [ ] `curl -X POST http://localhost:18600/memories/feedback -d '...'` 返回 200
- [ ] feedback 对象可通过 `mind/primitives/service.py` 的 `read()` 读回
- [ ] 已有 Phase B~J gate 不退化

#### 依赖

- 无前置依赖。可立即开始。

#### 估算

- **1 人 × 5-8 个工作日**

---

### α-2 对象优先级动态更新（Priority Signal Evolution）

**目标**：让对象优先级从静态写入变为可根据使用情况动态调整。

#### 任务分解

| 序号 | 子任务 | 要改的文件 | 新增的文件 | 说明 |
|---|---|---|---|---|
| α-2.1 | 扩展对象 metadata 动态信号 | `mind/kernel/schema.py` | — | 在 `REQUIRED_METADATA_FIELDS` 中**不**强制要求（可选 metadata），但在文档和 fixtures 中标注约定字段：`access_count (int, default 0)`、`feedback_positive_count (int)`、`feedback_negative_count (int)`、`last_accessed_at (str\|None)`、`effective_priority (float)`。 |
| α-2.2 | 新增优先级计算函数 | — | `mind/kernel/priority.py` | `compute_effective_priority(obj, feedback_records) -> float`。公式：`base_priority * 0.4 + recency_score * 0.2 + feedback_score * 0.3 + type_bonus * 0.1`。其中 `feedback_score = (positive - negative) / max(positive + negative, 1)`；`recency_score = 1.0 / (1 + days_since_last_access / 30)`。 |
| α-2.3 | 升级 `_replay_score()` | `mind/offline/replay.py` | — | 替换当前硬编码评分为调用 `compute_effective_priority()`。保留 type bonus 作为 backward compat，但增加 feedback 和 recency 维度。 |
| α-2.4 | 新增 `UPDATE_PRIORITY` offline job | `mind/offline_jobs.py`, `mind/offline/service.py` | `mind/offline/priority_update.py` | `OfflineJobKind.UPDATE_PRIORITY`。payload: `{ target_object_ids: list[str] }`。handler：读取该对象的所有 FeedbackRecord，计算新 effective_priority，更新对象 metadata（通过 insert 新版本实现 versioned update）。 |
| α-2.5 | 在 retrieve 路径中使用 effective_priority | `mind/kernel/retrieval.py` | — | `search_objects()` 的评分公式中，如果对象 metadata 含 `effective_priority`，优先使用 `effective_priority` 代替 `priority`。 |
| α-2.6 | 测试 | — | `tests/test_priority_evolution.py` | 覆盖：优先级计算公式、feedback 正负向影响、时间衰减、offline job 执行后优先级确实变化。 |

#### 验收标准

- [ ] 新写入的对象 priority 行为不变（backward compat）
- [ ] 有 FeedbackRecord 的对象 effective_priority 符合公式
- [ ] `select_replay_targets()` 对有 positive feedback 的对象排名上升
- [ ] UPDATE_PRIORITY job 可通过 offline worker 执行
- [ ] 全套 gate 不退化

#### 依赖

- **依赖 α-1**（需要 FeedbackRecord 作为数据源）

#### 估算

- **1 人 × 3-5 个工作日**

---

### α-3 Offline Worker 自触发机制（Job Scheduler）

**目标**：让 offline job 的创建从手动变为事件驱动自动化。

#### 任务分解

| 序号 | 子任务 | 要改的文件 | 新增的文件 | 说明 |
|---|---|---|---|---|
| α-3.1 | 定义 Scheduler 接口 | — | `mind/offline/scheduler.py` | `class OfflineJobScheduler`，方法：`on_episode_completed(store, episode_id)` → enqueue `REFLECT_EPISODE`；`on_feedback_accumulated(store, object_id, positive_count)` → 当 positive_count >= N (default 3) 时 enqueue `PROMOTE_SCHEMA`；`on_priority_stale(store, threshold_days)` → enqueue `UPDATE_PRIORITY`。 |
| α-3.2 | 集成进 write path | `mind/app/services/ingest.py` | — | 在 `remember()` / `ingest()` 方法末尾检查：如果本次写入的是 `TaskEpisode` 且 `metadata.result` 非空，调用 `scheduler.on_episode_completed()`。 |
| α-3.3 | 集成进 feedback path | `mind/app/services/feedback.py`（α-1.5 新增） | — | 在 `record_feedback()` 成功后，统计该 episode 下某对象的累计 positive feedback 数，达到阈值时调 `scheduler.on_feedback_accumulated()`。 |
| α-3.4 | API 端点：手动 enqueue | `mind/api/routers/jobs.py` | — | 新增 `POST /jobs/enqueue` 端点（或扩展已有 jobs router），允许外部系统手动提交任意 job kind。 |
| α-3.5 | 频率控制 | `mind/offline/scheduler.py` | — | 加入去重逻辑：同一 episode 在 pending/running 状态下不重复 enqueue `REFLECT_EPISODE`。用 `store.iter_offline_jobs(statuses=[PENDING, RUNNING])` 检查。 |
| α-3.6 | 配置项 | `mind/cli_config.py` | — | 新增配置项 `scheduler.auto_reflect_enabled: bool = True`、`scheduler.promote_threshold: int = 3`、`scheduler.priority_refresh_days: int = 7`。 |
| α-3.7 | 测试 | — | `tests/test_offline_scheduler.py` | 覆盖：episode 完成时自动 enqueue reflect、feedback 达标时自动 enqueue promote、去重逻辑、配置 disable 后不触发。 |

#### 验收标准

- [ ] 手动写入一个完成的 TaskEpisode 后，REFLECT_EPISODE job 自动出现在 job 队列中
- [ ] 对某对象连续提交 3 次 positive feedback 后，PROMOTE_SCHEMA job 自动出现
- [ ] 同一 episode 不会重复 enqueue
- [ ] `POST /jobs/enqueue` 可手动提交 job
- [ ] 全套 gate 不退化

#### 依赖

- **依赖 α-1**（feedback path 集成需要 feedback 机制就绪）
- 但 α-3.1 / α-3.4 / α-3.5 可与 α-1 并行开发

#### 估算

- **1 人 × 5-8 个工作日**

---

### α-4 闭环成长性评测指标（Growth Metrics）

**目标**：建立可量化的"记忆系统是否在成长"的评测指标。

#### 任务分解

| 序号 | 子任务 | 要改的文件 | 新增的文件 | 说明 |
|---|---|---|---|---|
| α-4.1 | 定义 `GrowthLift` 指标 | — | `mind/eval/growth_metrics.py` | `compute_growth_lift(with_offline_results, without_offline_results) -> float`。公式：`mean(with_pus) - mean(without_pus)`。需要 `LongHorizonBenchmarkRun` 的 A/B 对比数据。 |
| α-4.2 | 定义 `MemoryEfficiency` 指标 | `mind/eval/growth_metrics.py` | — | `compute_memory_efficiency(total_quality, task_count, total_objects) -> float`。公式：`(total_quality * task_count) / max(total_objects, 1)`。 |
| α-4.3 | 定义 `FeedbackCorrelation` 指标 | `mind/eval/growth_metrics.py` | — | `compute_feedback_correlation(positive_reuse_rate, negative_reuse_rate) -> float`。数值越高说明 feedback 信号确实影响了后续选择。 |
| α-4.4 | 集成到 eval runner | `mind/eval/runner.py` | — | 在 `LongHorizonScoreCard` 中新增可选字段：`growth_lift`、`memory_efficiency`。在 runner 中增加 A/B 对比模式支持。 |
| α-4.5 | 新增 growth eval 脚本 | — | `scripts/run_growth_eval.py` | CLI 入口，运行有/无 offline maintenance 的对比实验，输出 growth_lift 报告。 |
| α-4.6 | 测试 | — | `tests/test_growth_metrics.py` | 覆盖：指标计算正确性、边界值。 |

#### 验收标准

- [ ] `uv run python scripts/run_growth_eval.py` 可运行并输出 JSON 报告
- [ ] growth_lift > 0 时说明离线维护有正向作用
- [ ] 指标可被后续 gate 引用

#### 依赖

- **依赖 α-1**（需要 FeedbackRecord 数据流）
- 但指标定义和计算逻辑可先行编写

#### 估算

- **1 人 × 3-5 个工作日**

---

### α-S1 Session 上下文积累（穿插并行）

**目标**：同一 session 内多轮对话可以利用前序轮次的检索结果。

#### 任务分解

| 序号 | 子任务 | 要改的文件 | 新增的文件 | 说明 |
|---|---|---|---|---|
| α-S1.1 | 扩展 `AccessRunRequest` | `mind/access/contracts.py` | — | 新增可选字段 `session_context: SessionAccessContext \| None = None`。`SessionAccessContext` 包含 `previous_used_object_ids: list[str]`、`previous_query_summaries: list[str]`、`turn_index: int`。 |
| α-S1.2 | 在 workspace 构建时注入 session 上下文 | `mind/access/service.py`, `mind/workspace/builder.py` | — | 如果 `session_context` 存在：(a) retrieval 时将 previous queries 追加为 query expansion；(b) workspace 构建时将 previous_used_object_ids 中未被命中的对象以低优先级加入候选池。 |
| α-S1.3 | App 层传递 session context | `mind/app/services/access.py` | — | 从 `AppRequest.session` 中提取 session 历史，构造 `SessionAccessContext`。 |
| α-S1.4 | 测试 | — | `tests/test_session_context.py` | 覆盖：有 session context 时 workspace 中出现前序对象；无 session context 时行为不变。 |

#### 验收标准

- [ ] 多轮 access run 中，后续轮次的 workspace 可包含前序轮次的 used objects
- [ ] 无 session context 时完全 backward compat

#### 依赖

- 无前置依赖，可与 α-1 并行

#### 估算

- **1 人 × 3-5 个工作日**

---

### α-S2 系统健康度监控（穿插并行）

**目标**：提供系统级记忆健康状态视图。

#### 任务分解

| 序号 | 子任务 | 要改的文件 | 新增的文件 | 说明 |
|---|---|---|---|---|
| α-S2.1 | 定义健康指标 | — | `mind/kernel/health.py` | `compute_health_report(store) -> HealthReport`。输出：各 object_type 数量、各 status 分布、平均 priority、pending job 数量、orphan reference 数量（source_refs 指向不存在的对象）。 |
| α-S2.2 | CLI 命令 | `mind/product_cli.py` | — | 新增 `mind status --detailed` 子命令，输出 health report。 |
| α-S2.3 | API 端点 | `mind/api/routers/system.py` | — | 扩展 `GET /system/status` 支持 `?detailed=true` 参数返回 health report。 |
| α-S2.4 | 测试 | — | `tests/test_health_report.py` | 覆盖：空 store、有对象 store、orphan 检测。 |

#### 验收标准

- [ ] `mind status --detailed` 输出各类型对象计数和状态分布
- [ ] orphan reference 检测工作正常

#### 依赖

- 无前置依赖，可立即开始

#### 估算

- **1 人 × 2-3 个工作日**

---

## Phase β：提升核心质量（第 2-4 月）

---

### β-1 Dense Retrieval（真正的向量检索）

**目标**：将检索从 deterministic hash embedding 升级为真实语义向量。

#### 任务分解

| 序号 | 子任务 | 要改的文件 | 新增的文件 | 说明 |
|---|---|---|---|---|
| β-1.1 | 抽象 Embedding 接口 | — | `mind/kernel/embedding.py` | `class EmbeddingProvider(Protocol): def embed(self, texts: list[str]) -> list[tuple[float, ...]]`。实现：`LocalHashEmbedding`（当前行为）、`SentenceTransformerEmbedding`（本地模型）、`OpenAIEmbedding`（API）。 |
| β-1.2 | 配置层 | `mind/cli_config.py` | — | 新增 `embedding.provider: str = "local-hash"`、`embedding.model_name: str = "all-MiniLM-L6-v2"`、`embedding.dimension: int = 384`。 |
| β-1.3 | DB migration（条件性） | — | `alembic/versions/20260314_0010_embedding_dimension.py` | 如果当前 `EMBEDDING_DIM=64` 不够用（sentence-transformers 通常 384/768），需要 migration 扩展 pgvector 维度。**注意**：pgvector 列维度变更需要 drop + recreate。设计为可逐步迁移：新增一列 `dense_embedding vector(384)`，保留旧列。 |
| β-1.4 | 写入侧：双 embedding | `mind/kernel/postgres_store.py` | — | `_insert_object_into` 方法在写入时同时生成 dense embedding（如果 provider 可用）。写入到 `object_embeddings` 表的新列或新行（`embedding_model` 字段区分）。 |
| β-1.5 | 检索侧：hybrid scoring | `mind/kernel/retrieval.py` | — | `search_objects()` 的评分改为：`final_score = w_lexical * trgm_score + w_dense * cosine_similarity + w_priority * priority_score`。权重可配置，默认 `w_lexical=0.3, w_dense=0.5, w_priority=0.2`。 |
| β-1.6 | Postgres store search 改造 | `mind/kernel/postgres_store.py` | — | `search_latest_objects()` 增加 pgvector ANN 查询路径。当 `query_embedding` 为 dense embedding 时使用 `<=>` 距离操作符。 |
| β-1.7 | 新增 REFRESH_EMBEDDINGS offline job | `mind/offline_jobs.py`, `mind/offline/service.py` | — | `OfflineJobKind.REFRESH_EMBEDDINGS`。handler：扫描缺少 dense embedding 的对象，批量生成并写入。适用于存量数据迁移。 |
| β-1.8 | pyproject.toml 依赖 | `pyproject.toml` | — | 新增可选依赖组 `[project.optional-dependencies] dense = ["sentence-transformers>=2.2", "torch>=2.0"]`。API embedding 不需要本地 torch。 |
| β-1.9 | Retrieval benchmark 扩展 | `mind/fixtures/retrieval_benchmark.py` | — | 在 `RetrievalBenchmark` 中新增 dense retrieval 相关 case，验证 hybrid retrieval 的 recall 提升。 |
| β-1.10 | 测试 | — | `tests/test_dense_retrieval.py` | 覆盖：embedding provider 切换、hybrid scoring 正确性、fallback 到 local-hash、pgvector ANN 查询。 |

#### 验收标准

- [ ] 配置 `embedding.provider=sentence-transformer` 后，新写入对象自动生成 384 维 dense embedding
- [ ] hybrid retrieval recall@10 相比纯 lexical 提升（在 RetrievalBenchmark 上度量）
- [ ] `embedding.provider=local-hash` 时行为完全 backward compat
- [ ] REFRESH_EMBEDDINGS job 可补充存量对象的 dense embedding
- [ ] 全套 gate 不退化

#### 依赖

- 无强依赖，但建议在 α-1/α-2 之后开始（有 feedback 数据可验证检索改进效果）

#### 估算

- **1 人 × 8-12 个工作日**

---

### β-2 输入冲突检测（Input Conflict Detection）

**目标**：在写入后异步检测新信息与已有记忆的关系（重复/矛盾/更新/全新）。

#### 任务分解

| 序号 | 子任务 | 要改的文件 | 新增的文件 | 说明 |
|---|---|---|---|---|
| β-2.1 | 定义冲突关系枚举 | — | `mind/primitives/conflict.py` | `class ConflictRelation(StrEnum): DUPLICATE, REFINE, CONTRADICT, SUPERSEDE, NOVEL`。`@dataclass class ConflictDetectionResult: relation, confidence, neighbor_id, explanation`。 |
| β-2.2 | 实现冲突检测逻辑 | `mind/primitives/conflict.py` | — | `detect_conflicts(store, new_object, embedding_provider, top_k=3) -> list[ConflictDetectionResult]`。步骤：(1) 对 new_object 做 retrieve top-3 近邻；(2) 对每个近邻用简单规则或 LLM 判断关系；(3) 返回结果列表。初始版本用规则：cosine_similarity > 0.95 → DUPLICATE，> 0.85 → REFINE，content 含否定关键词 → CONTRADICT，else → NOVEL。 |
| β-2.3 | 异步集成到 write path | `mind/app/services/ingest.py` | — | 在 `remember()` 成功写入后，**异步**调用 `detect_conflicts()`。检测结果写入对象 metadata 的 `conflict_candidates` 字段（通过 insert 新版本）。 |
| β-2.4 | 新增 RESOLVE_CONFLICT offline job | `mind/offline_jobs.py`, `mind/offline/service.py` | — | `OfflineJobKind.RESOLVE_CONFLICT`。payload: `{ object_id, conflict_candidates }`。handler：对高置信度 CONTRADICT 关系，可通过 LLM 判断是否需要标记旧对象为 deprecated。 |
| β-2.5 | Scheduler 集成 | `mind/offline/scheduler.py` | — | 当 `detect_conflicts()` 返回 CONTRADICT 结果时，自动 enqueue `RESOLVE_CONFLICT`。 |
| β-2.6 | 测试 | — | `tests/test_conflict_detection.py` | 覆盖：各种关系的检测、异步执行不阻塞写入、RESOLVE_CONFLICT job 流程。 |

#### 验收标准

- [ ] 写入重复内容后，对象 metadata 中出现 `conflict_candidates` 且 relation=DUPLICATE
- [ ] 写入矛盾内容后，RESOLVE_CONFLICT job 自动 enqueue
- [ ] 写入路径延迟不因冲突检测显著增加（异步执行）
- [ ] 全套 gate 不退化

#### 依赖

- **依赖 β-1**（冲突检测质量依赖 dense embedding 的近邻搜索质量）
- 如果 β-1 尚未完成，可以先用 lexical retrieval 做降级版本

#### 估算

- **1 人 × 6-10 个工作日**

---

### β-3 Workspace 选择策略增强（Evidence Diversity）

**目标**：workspace slot 选择从纯分数排序升级为多样性感知选择。

#### 任务分解

| 序号 | 子任务 | 要改的文件 | 新增的文件 | 说明 |
|---|---|---|---|---|
| β-3.1 | 定义 slot allocation policy | — | `mind/workspace/policy.py` | `class SlotAllocationPolicy`，包含约束：`min_raw_evidence_slots: int = 1`（至少 1 个 RawRecord slot）、`min_diverse_episode_slots: int = 1`（至少 1 个来自不同 episode 的对象）、`include_conflict_evidence: bool = True`（如有 conflict_candidates，纳入矛盾证据）。 |
| β-3.2 | 改造 `WorkspaceBuilder.build()` | `mind/workspace/builder.py` | — | 在现有的 `ranked_candidates.sort(...)` + `selected = ranked_candidates[:slot_limit]` 逻辑之后，增加 diversity rebalancing 逻辑。步骤：(1) 先按分数选满 slot；(2) 检查是否满足 policy 约束；(3) 如不满足，从 remaining candidates 中替换 lowest-priority slot 以满足约束。 |
| β-3.3 | 按 AccessMode 配置不同 policy | `mind/access/service.py` | — | `_MODE_PLANS` 扩展支持 `slot_policy` 参数。Flash 不做 diversity（无 workspace），Recall 用默认 policy，Reconstruct/Reflective 使用更严格的 diversity 约束。 |
| β-3.4 | 扩展 benchmark：diversity metric | `mind/access/benchmark.py` | — | 在 `AccessBenchmarkAggregate` 中新增 `evidence_diversity_score`：衡量 workspace 中 object_type 的 Shannon entropy + episode 多样性。 |
| β-3.5 | 测试 | — | `tests/test_workspace_diversity.py` | 覆盖：全部候选来自同一 episode 时 diversity rebalancing 生效、conflict evidence 被纳入、constraint 不满足时 graceful degradation。 |

#### 验收标准

- [ ] Recall 模式 workspace 中至少有 1 个不同 episode 的对象（如可用）
- [ ] 有 conflict_candidates 标记的场景，矛盾证据被纳入 workspace
- [ ] benchmark diversity_score 相比改造前提升
- [ ] 全套 gate 不退化

#### 依赖

- **依赖 β-2**（利用 conflict_candidates 信号）
- 但核心 diversity logic 可先独立开发

#### 估算

- **1 人 × 5-8 个工作日**

---

### β-4 Promotion Pipeline + Proposal Lifecycle

**目标**：让 SchemaNote 的晋升从一步到位变为 proposed → verified → committed 三阶段。

#### 任务分解

| 序号 | 子任务 | 要改的文件 | 新增的文件 | 说明 |
|---|---|---|---|---|
| β-4.1 | 扩展 SchemaNote metadata | `mind/kernel/schema.py` | — | 在 `REQUIRED_METADATA_FIELDS["SchemaNote"]` 中新增可选字段 `proposal_status`（值域 `proposed \| verified \| committed \| rejected`，默认 `committed` 以 backward compat）。 |
| β-4.2 | 修改 promotion 输出 | `mind/offline/promotion.py`, `mind/offline/service.py` | — | `_process_promote_schema()` 生成的 SchemaNote 的 `proposal_status` 改为 `proposed`（而非直接进入 active）。 |
| β-4.3 | 新增 VERIFY_PROPOSAL offline job | `mind/offline_jobs.py`, `mind/offline/service.py` | — | `OfflineJobKind.VERIFY_PROPOSAL`。payload: `{ schema_note_id }`。handler：(1) 读取 SchemaNote 的 evidence_refs；(2) 检查是否有跨 episode 反证（通过 retrieval 搜索否定条件）；(3) 用 LLM 做结构化判断（可选，高优先级候选才走 LLM）；(4) 通过则 update `proposal_status = verified → committed`，不通过则 `rejected`。 |
| β-4.4 | Scheduler 集成 | `mind/offline/scheduler.py` | — | 当 PROMOTE_SCHEMA job 成功创建 proposed SchemaNote 后，自动 enqueue `VERIFY_PROPOSAL`。 |
| β-4.5 | 检索过滤 | `mind/kernel/retrieval.py` | — | `matches_retrieval_filters()` 默认排除 `proposal_status in (proposed, rejected)` 的 SchemaNote。仅 `verified` 和 `committed` 参与检索。 |
| β-4.6 | 测试 | — | `tests/test_promotion_lifecycle.py` | 覆盖：promotion 产出 proposed 对象、verify 通过流 committed、verify 不通过流 rejected、rejected 对象不参与检索。 |

#### 验收标准

- [ ] 新 promote 的 SchemaNote 状态为 `proposed`
- [ ] VERIFY_PROPOSAL job 执行后，SchemaNote 变为 `committed` 或 `rejected`
- [ ] `retrieve` 结果中不包含 `proposed` / `rejected` 状态的 SchemaNote
- [ ] 已有的 `committed` SchemaNote（历史数据）行为不变
- [ ] 全套 gate 不退化

#### 依赖

- **依赖 α-3**（需要 scheduler 自动创建 VERIFY_PROPOSAL job）

#### 估算

- **1 人 × 8-12 个工作日**

---

### β-5 Auto 模式决策增强

**目标**：`auto` 模式从纯规则驱动升级为 scouting + 历史感知的两阶段决策。

#### 任务分解

| 序号 | 子任务 | 要改的文件 | 新增的文件 | 说明 |
|---|---|---|---|---|
| β-5.1 | 实现 scouting retrieval | `mind/access/service.py` | — | 在 `_run_auto()` 中，先以 Flash 级别做一次 lightweight scouting retrieval（top-3）。读取返回结果的 coverage（不同 episode 数）、conflict 信号（是否有 conflict_candidates）、evidence density。 |
| β-5.2 | 改造 `_choose_initial_auto_mode()` | `mind/access/service.py` | — | 增加 scouting 结果驱动的分支：(a) scouting 命中 0 条 → FLASH（无可用记忆，不用走深）；(b) scouting 有 conflict → RECONSTRUCT；(c) scouting 覆盖单 episode → RECALL；(d) scouting 覆盖多 episode → RECONSTRUCT。 |
| β-5.3 | 历史档位缓存 | — | `mind/access/mode_history.py` | `class ModeHistoryCache`。维护 `task_family → Counter[AccessMode]` 的统计，基于 FeedbackRecord 中 quality_signal 加权。供 auto 模式做历史参考。 |
| β-5.4 | Budget 感知降级 | `mind/access/service.py` | — | 在 `_choose_auto_switch()` 中增加 budget 判断：如果执行到 Recall 阶段时 token cost 已超过预估的 80%，不再 upgrade。 |
| β-5.5 | 测试 | — | `tests/test_auto_mode_enhanced.py` | 覆盖：scouting 空结果 → Flash、conflict → Reconstruct、budget 压力 → 不 upgrade、历史缓存影响。 |

#### 验收标准

- [ ] auto 模式在"无记忆"场景下选择 Flash（而非当前默认 Recall）
- [ ] auto 模式在"有冲突"场景下升级到 Reconstruct
- [ ] scouting 增加的额外 retrieval 调用不超过 Flash 级别成本
- [ ] AccessDepthBench auto_aqs_drop 不恶化
- [ ] 全套 gate 不退化

#### 依赖

- **依赖 α-1 + α-2**（feedback 数据和优先级信号为 scouting 质量提供基础）

#### 估算

- **1 人 × 6-10 个工作日**

---

### β-S1 记忆可解释性输出（穿插并行）

**目标**：用户可以看到"这个回答基于哪些记忆"。

#### 任务分解

| 序号 | 子任务 | 要改的文件 | 说明 |
|---|---|---|---|
| β-S1.1 | 扩展 AccessRunResponse | `mind/access/contracts.py` | 新增字段 `evidence_summary: list[EvidenceSummaryItem] = []`。`EvidenceSummaryItem`: `{ object_id, object_type, brief, relevance_score }`。 |
| β-S1.2 | 在 access service 中生成 evidence summary | `mind/access/service.py` | 在 `_build_response()` 阶段，从 selected_objects 中提取 top-3 生成 brief summary。 |
| β-S1.3 | Frontend 展示 | `frontend/app.js`, `frontend/styles.css` | 在回答区域下方展示 evidence panel。 |
| β-S1.4 | API 透传 | `mind/app/services/access.py` | 在 response 中透传 evidence_summary。 |

#### 验收标准

- [ ] API 返回的 access response 中包含 evidence_summary
- [ ] 前端可见 evidence 面板

#### 依赖

- 无强依赖

#### 估算

- **1 人 × 3-5 个工作日**

---

## Phase γ：扩展能力边界（第 4-8 月）

---

### γ-1 PolicyNote / PreferenceNote 新对象类型

**目标**：为"操作策略"和"用户偏好"引入专门的一等公民记忆类型。

#### 任务分解

| 序号 | 子任务 | 要改的文件 | 新增的文件 | 说明 |
|---|---|---|---|---|
| γ-1.1 | Schema 定义 | `mind/kernel/schema.py` | — | `CORE_OBJECT_TYPES` 新增 `"PolicyNote"`, `"PreferenceNote"`。`REQUIRED_METADATA_FIELDS["PolicyNote"] = ("trigger_condition", "action_pattern", "evidence_refs", "confidence", "applies_to_scope")`；`REQUIRED_METADATA_FIELDS["PreferenceNote"] = ("preference_key", "preference_value", "strength", "evidence_refs")`。 |
| γ-1.2 | Promotion 策略 | `mind/offline/promotion.py` | — | `assess_policy_promotion()` 和 `assess_preference_promotion()`。门槛高于 SchemaNote：需要至少 3 个不同 episode 的趋同证据。 |
| γ-1.3 | 新 offline job kinds | `mind/offline_jobs.py`, `mind/offline/service.py` | — | `PROMOTE_POLICY`, `PROMOTE_PREFERENCE`。复用 verify → commit 管线。 |
| γ-1.4 | Workspace 感知 | `mind/workspace/builder.py` | — | 当 task 含有决策关键词时，PolicyNote 获得 slot 加权。 |
| γ-1.5 | Golden fixtures + 测试 | `mind/fixtures/golden_episode_set.py` | `tests/test_new_object_types.py` | 完整样例 + CRUD + promotion + retrieval 测试。 |

#### 验收标准

- [ ] PolicyNote / PreferenceNote 可写入、检索、纳入 workspace
- [ ] Promotion 门槛高于 SchemaNote
- [ ] 全套 gate 不退化

#### 依赖

- **依赖 β-4**（Proposal lifecycle 管线复用）

#### 估算

- **1 人 × 10-15 个工作日**

---

### γ-2 Graph-Augmented Retrieval

**目标**：利用 LinkEdge 做 graph walk expand。

#### 任务分解

| 序号 | 子任务 | 要改的文件 | 新增的文件 | 说明 |
|---|---|---|---|---|
| γ-2.1 | 邻接表构建 | — | `mind/kernel/graph.py` | `build_adjacency_index(store) -> dict[str, list[str]]`。从所有 active LinkEdge 构建双向邻接表。 |
| γ-2.2 | Graph walk | `mind/kernel/graph.py` | — | `expand_by_graph(seed_ids, adjacency, hops=1, max_expand=10) -> list[str]`。BFS expand。 |
| γ-2.3 | 集成到 access service | `mind/access/service.py` | — | Recall 及以上档位的 retrieve 后，对 candidate_ids 做 1-hop expand。Reconstruct 做 2-hop。 |
| γ-2.4 | 新增 DISCOVER_LINKS offline job | `mind/offline_jobs.py`, `mind/offline/service.py` | — | 对高优先级对象做 embedding 近邻搜索，自动创建 proposed LinkEdge。 |
| γ-2.5 | 测试 | — | `tests/test_graph_retrieval.py` | 覆盖：expand 正确性、环路处理、max_expand 限制。 |

#### 验收标准

- [ ] Recall 模式 retrieve 后增加 graph expand 候选
- [ ] expand 不引入已 concealed 对象
- [ ] DISCOVER_LINKS 可自动发现跨 episode 关联

#### 依赖

- **依赖 β-1**（dense embedding 提升 DISCOVER_LINKS 质量）

#### 估算

- **1 人 × 8-12 个工作日**

---

### γ-3 分层模型路由

**目标**：不同 capability 请求可以路由到不同模型。

#### 任务分解

| 序号 | 子任务 | 要改的文件 | 说明 |
|---|---|---|---|
| γ-3.1 | Per-capability config | `mind/capabilities/contracts.py` | 新增 `CapabilityRoutingConfig: dict[CapabilityKind, CapabilityProviderConfig]`。 |
| γ-3.2 | Service routing | `mind/capabilities/service.py` | `_invoke()` 根据 request type 选择对应 provider config。 |
| γ-3.3 | CLI config | `mind/cli_config.py` | 新增 `model_routing` 配置段。 |
| γ-3.4 | 测试 | `tests/test_model_routing.py` | 覆盖：summarize 走小模型、answer 走大模型、fallback 逻辑不变。 |

#### 验收标准

- [ ] 可配置 summarize/reflect 走不同 provider
- [ ] 无配置时 backward compat

#### 依赖

- 无强依赖，**可随时启动**

#### 估算

- **1 人 × 5-8 个工作日**

---

### γ-4 Structured Artifact Memory

**目标**：为长文档/长 episode 建立树状索引。

#### 任务分解

| 序号 | 子任务 | 要改的文件 | 新增的文件 | 说明 |
|---|---|---|---|---|
| γ-4.1 | ArtifactIndex 对象类型 | `mind/kernel/schema.py` | — | 新对象类型，metadata: `parent_object_id, section_id, parent_section_id, heading, summary, depth, content_range`。 |
| γ-4.2 | 索引构建 | — | `mind/offline/artifact_indexer.py` | 对长对象（content 长度 > 阈值）做 heading/section 切分，递归构建树状索引。 |
| γ-4.3 | Tree-guided retrieval | `mind/kernel/retrieval.py` | — | 命中 ArtifactIndex 时，先返回顶层 section summary，支持 drill-down expand。 |
| γ-4.4 | REBUILD_ARTIFACT_INDEX offline job | `mind/offline_jobs.py`, `mind/offline/service.py` | — | 对新长对象自动建索引。 |
| γ-4.5 | 测试 | — | `tests/test_artifact_memory.py` | 覆盖：长文档索引构建、tree navigate、drill-down。 |

#### 验收标准

- [ ] 长文档可被索引为树状结构
- [ ] Reconstruct 模式支持 tree-guided 检索
- [ ] 短文档不受影响

#### 依赖

- **依赖 β-1**（dense embedding 提升 section 检索质量）

#### 估算

- **1-2 人 × 15-25 个工作日**（最复杂的任务）

---

### γ-5 记忆衰减与自动归档

**目标**：长期未使用且无正面反馈的对象自动归档。

#### 任务分解

| 序号 | 子任务 | 要改的文件 | 说明 |
|---|---|---|---|
| γ-5.1 | AUTO_ARCHIVE offline job | `mind/offline_jobs.py`, `mind/offline/service.py` | 条件：last_accessed_at > 90天 且 feedback_positive_count == 0 且类型为 RawRecord/SummaryNote。执行：status → archived。 |
| γ-5.2 | Scheduler 集成 | `mind/offline/scheduler.py` | 定期（每周）enqueue AUTO_ARCHIVE 扫描。 |
| γ-5.3 | 归档可恢复 | `mind/product_cli.py` | `mind unarchive --object-id ...`。 |
| γ-5.4 | ArchiveReport | `mind/eval/growth_metrics.py` | 输出归档数量、误归档率（被 unarchive 的比例）。 |
| γ-5.5 | 测试 | `tests/test_auto_archive.py` | 覆盖：满足条件归档、不满足不归档、archived 对象不参与默认检索。 |

#### 验收标准

- [ ] 超过 90 天未访问且无正面反馈的 RawRecord 被自动归档
- [ ] archived 对象可通过 Reconstruct/Reflective 模式显式召回
- [ ] unarchive 可恢复

#### 依赖

- **依赖 α-2**（需要 last_accessed_at 和 feedback count 信号）

#### 估算

- **1 人 × 5-8 个工作日**

---

## 总进度甘特图（概念级）

```
Month 1     Month 2     Month 3     Month 4     Month 5     Month 6+
─────────── ─────────── ─────────── ─────────── ─────────── ───────────
[α-1 Feedback   ]
    [α-2 Priority   ]
[α-3 Scheduler      ]
    [α-4 Eval       ]
[α-S1 Session  ]
[α-S2 Health ]
                [β-1 Dense Retrieval        ]
                    [β-2 Conflict Detection     ]
                        [β-3 Workspace Diversity    ]
                    [β-4 Promotion Lifecycle         ]
                            [β-5 Auto Mode          ]
                [β-S1 Evidence UI  ]
                                        [γ-1 New Types          ]
                                        [γ-2 Graph Retrieval    ]
                                    [γ-3 Model Routing  ]
                                                [γ-4 Artifact   ·····]
                                            [γ-5 Archive    ]
```

---

## 风险登记簿

| ID | 风险 | 影响 | 缓解措施 |
|---|---|---|---|
| R1 | FeedbackRecord 引入后 object_versions 表膨胀 | 中 | 设置 feedback 对象的自动过期策略；或独立表存储 |
| R2 | Dense embedding 引入外部依赖（torch / API） | 中 | 保留 local-hash fallback；API embedding 作为首选（无 GPU 依赖） |
| R3 | 冲突检测 false positive 导致误标 | 高 | 初始版用高阈值（cosine > 0.95 → DUPLICATE）；LLM 验证只对高优先级对象 |
| R4 | Promotion lifecycle 增加延迟 | 中 | proposed → committed 路径为异步；不影响在线查询延迟 |
| R5 | Auto scouting 多一次 retrieval 增加成本 | 低 | scouting 使用 Flash 级别（top-3），成本极低 |
| R6 | γ-4 Artifact indexer 对长文档成本高 | 高 | 先只对 > 5000 token 的对象建索引；设置 per-object 索引预算上限 |
| R7 | Offline scheduler 频率控制失效导致 job 风暴 | 中 | 去重逻辑 + 每分钟 max enqueue 限速 + PENDING job 上限 |

---

## 每日站会检查清单

执行期间，每日确认：

1. 当前在做哪个编号的子任务？
2. 该子任务涉及的文件是否已读完并理解？
3. 是否有未预期的 gate 退化？
4. 是否需要调整子任务粒度或依赖关系？
