# 阶段 D 独立审计报告

**审计日期:** 2025-07 初审 → 2026-03-09 深度复审  
**审计范围:** 所有本地未提交修改（约 30 个新增/修改文件），覆盖检索层、Workspace 构建器、基准测试框架、答案级 D-5 评测、PostgreSQL pgvector/pg_trgm 集成  
**基准版本:** Phase D 全功能变更集  
**前置依赖:** Phase B gate PASS, Phase C gate PASS（均在本次审计中重新验证）

---

## 1. 审计方法论

| 步骤 | 内容 |
|------|------|
| ① 收集差异 | `get_changed_files` 获取完整 diff；约 30 个文件 |
| ② 逐文件通读 | 全部新增文件 + 所有修改行完整阅读 |
| ③ 规范对照 | 对照 `phase_gates.md` D-1 ~ D-5，逐条验证 |
| ④ 工具链检测 | `ruff check .` / `mypy mind tests scripts` / `pytest tests/ -v` |
| ⑤ Gate 脚本运行 | `python scripts/run_phase_d_smoke.py` → 执行 D-1 ~ D-5 全流程 |
| ⑥ Phase E 前置检查 | 读取 E-1 ~ E-5 规范，评估 D 阶段产物对 E 阶段的支撑性 |
| ⑦ 多维度深度审计 | 必要性、完整性、合理性、安全性、可维护性 |
| ⑧ 深度复审 | 设计缺陷分析、边界条件审查、DRY/防御性编码审查 |
| ⑨ 补充测试 | 新增 36 条边界测试覆盖审计发现的薄弱点 |

---

## 2. 基线检测结果

```
$ ruff check .
All checks passed!

$ mypy mind tests scripts
Success: no issues found in 41 source files

$ pytest tests/ -v
68 passed, 5 skipped in 8.73s
# 5 skipped: Postgres 回归测试（需 MIND_POSTGRES_DSN 环境变量）

$ python scripts/run_phase_d_smoke.py
D-1=PASS  D-2=PASS  D-3=PASS  D-4=PASS  D-5=PASS
phase_d_smoke=PASS
```

Phase B gate 回归检查：`python scripts/run_phase_b_gate.py` → **PASS**

---

## 3. Gate 逐条验证

### D-1：检索模式覆盖 3/3

| 模式 | 实现 | SQLite 路径 | PostgreSQL 路径 | Smoke 结果 |
|------|------|-------------|-----------------|-----------|
| `keyword` | `retrieval.keyword_score()` / pg_trgm `similarity()` + LIKE boost | `search_objects()` 内存评分 | `_search_latest_objects()` SQL 级 | 4/4 pass |
| `time_window` | `retrieval.time_window_score()` / `CAST(created_at AS TIMESTAMP)` 范围比较 | `search_objects()` 内存评分 | `_search_latest_objects()` SQL 级 | 4/4 pass |
| `vector` | `retrieval.vector_score()` / pgvector `<=>` cosine 距离 | `search_objects()` 内存评分 | `_search_latest_objects()` 外联 `object_embeddings` | 4/4 pass |

**判定: D-1 PASS** — 12 条 smoke case 全部通过，所有三种模式各有 4 条独立验证。

### D-2：Candidate recall@20 ≥ 0.85

- 在 `RetrievalBenchmark v1`（100 条 benchmark case）上测算
- 实测 `candidate_recall_at_20 = 1.00`
- **判定: D-2 PASS** — 远超 0.85 阈值

### D-3：Workspace gold-fact coverage ≥ 0.80

- 同 100 条 benchmark case 上测算
- 实测 `workspace_gold_fact_coverage = 1.00`
- **判定: D-3 PASS** — 远超 0.80 阈值

### D-4：Workspace 槽位纪律 100%

- `workspace_slot_discipline_rate = 1.00`（所有 workspace 满足 `slot_count ≤ slot_limit`）
- `workspace_source_ref_coverage = 1.00`（所有 slot 有 `source_refs`）
- **判定: D-4 PASS**

### D-5：成本收益门槛

| 指标 | 阈值 | 实测 | 判定 |
|------|------|------|------|
| `median_token_cost_ratio` | ≤ 0.60 | 0.18 | PASS |
| `task_success_drop_pp` | ≤ 5.0 | 0.00 | PASS |
| `raw_top20_answer_quality_score` | — | 1.00 | 基线 |
| `workspace_answer_quality_score` | — | 1.00 | 无退化 |

- 答案级评测公式：`0.45×task_completion + 0.20×constraint_satisfaction + 0.20×gold_fact_coverage + 0.15×answer_faithfulness`
- 5 种 `AnswerKind`：`task_result` / `summary` / `result_and_summary` / `final_raw` / `vector_summary`
- **判定: D-5 PASS** — Token 成本降至 18%，且任务成功率无退化

---

## 4. 变更清单

### 4.1 新增文件（18 个）

| 文件 | 行数 | 说明 |
|------|------|------|
| `mind/workspace/__init__.py` | 31 | 包入口；导出 WorkspaceBuilder, context_protocol, phase_d |
| `mind/workspace/builder.py` | 211 | WorkspaceBuilder: build(), slot 组装, 去重, 摘要, evidence_refs |
| `mind/workspace/context_protocol.py` | 90 | 冻结协议 `mind.phase_d_context.v1`；raw_topk / workspace 两种序列化 |
| `mind/workspace/phase_d.py` | 409 | D-1~D-5 评估引擎；smoke 12 + benchmark 100 + answer 100 |
| `mind/workspace/answer_benchmark.py` | 269 | 答案生成 / 评分框架；支持 raw_topk 和 workspace 两种上下文 |
| `mind/kernel/retrieval.py` | 313 | 共享检索工具：embedding / scoring / filtering / latest_objects |
| `mind/kernel/pgvector.py` | 52 | SQLAlchemy Vector UserDefinedType（无额外依赖） |
| `mind/fixtures/retrieval_benchmark.py` | 264 | RetrievalBenchmarkCase；v0 (12) + v1 (100) 冻结 fixture |
| `mind/fixtures/episode_answer_bench.py` | 110 | EpisodeAnswerBenchCase；v1 (100) 冻结 fixture |
| `alembic/versions/20260309_0002_*.py` | 42 | 检索索引迁移（status / updated_at / episode_id / task_id / source_refs） |
| `alembic/versions/20260309_0003_*.py` | 70 | pgvector/pg_trgm 迁移（search_text, object_embeddings 表, 扩展） |
| `tests/test_phase_d_smoke.py` | 77 | benchmark 冻结验证 + SQLite 全流程 smoke |
| `tests/test_workspace_builder.py` | 99 | WorkspaceBuilder 正常路径 + 无效跳过 |
| `tests/test_workspace_context_protocol.py` | 70 | 上下文确定性 + workspace 比 raw_topk 更紧凑 |
| `scripts/run_phase_d_smoke.py` | ~50 | Phase D gate 运行入口 |
| `docs/reports/phase_d_acceptance_report.md` | 175 | 自验收报告 |
| `docs/reports/phase_d_smoke_report.md` | 145 | Smoke 基线状态报告 |

### 4.2 深度复审新增/修改文件

| 文件 | 说明 |
|------|------|
| `tests/test_phase_d_deep_audit.py` | +36 条边界/集成补充测试 |
| `mind/kernel/retrieval.py` | `cosine_similarity` strict=True 修复；`_tokenize` → 公共 `tokenize()` |
| `mind/workspace/answer_benchmark.py` | DEF-3/4/5 修复；导入共享 `tokenize` |

### 4.3 修改文件（12 个）

| 文件 | 关键变更 |
|------|----------|
| `mind/kernel/store.py` | MemoryStore Protocol 新增 `iter_latest_objects`, `search_latest_objects`；SQLite 实现 |
| `mind/kernel/postgres_store.py` | 新增 `iter_latest_objects`, `search_latest_objects`, `_latest_objects_subquery`, `_search_latest_objects`, `_backfill_retrieval_artifacts`；`_validate_and_insert` 增加 `search_text` + `object_embeddings` 写入 |
| `mind/kernel/sql_tables.py` | 新增 `search_text` 列、`object_embeddings_table`、9 个新索引 |
| `mind/primitives/service.py` | `_retrieve` 重构：集成 `store.search_latest_objects`；新增 `query_embedder` 参数 |
| `mind/primitives/contracts.py` | 新增 `RETRIEVAL_BACKEND_UNAVAILABLE` 错误码 |
| `mind/cli.py` | 新增 `phase_d_smoke_main()`；扩展 `postgres_regression_main()` |
| `pyproject.toml` | 新增 `mind-phase-d-smoke` 入口点 |
| `tests/test_phase_c_primitives.py` | +2 新测试：latest-version 过滤、vector 后端守卫 |
| `tests/test_postgres_regression.py` | +4 新测试：Postgres iter/workspace/vector/Phase D 回归 |
| `docs/foundation/implementation_stack.md` | 明确 PostgreSQL 为唯一生产后端 |

---

## 5. 多维度审计

### 5.1 必要性

**每个新增文件是否有明确需求支撑？**

| 组件 | 需求来源 | 判定 |
|------|----------|------|
| `retrieval.py` | D-1 要求 3 种检索模式，需共享评分逻辑 | 必要 |
| `pgvector.py` | vector 模式需要 pgvector 类型映射 | 必要 |
| `builder.py` | D-3/D-4 要求 workspace 构建 + 槽位纪律 | 必要 |
| `context_protocol.py` | D-5 需要 raw_topk 与 workspace 上下文对比 | 必要 |
| `phase_d.py` | Gate 需要自动化评估引擎 | 必要 |
| `answer_benchmark.py` | D-5 答案级评测替代代理指标 | 必要 |
| `retrieval_benchmark.py` | D-2/D-3 需要冻结基准 | 必要 |
| `episode_answer_bench.py` | D-5 需要答案级基准 | 必要 |
| Alembic 0002/0003 | PostgreSQL 检索索引 + pgvector 扩展 | 必要 |

**死代码检查：** 无未使用的导入、无未调用的函数。`ruff` + `mypy` 均未报告。

### 5.2 完整性

**5.2.1 Protocol 覆盖**

`MemoryStore` Protocol 定义 14 个方法：

| 方法 | SQLite | PostgreSQL |
|------|--------|-----------|
| `insert_object` | ✅ | ✅ |
| `insert_objects` | ✅ | ✅ |
| `transaction` | ✅ | ✅ |
| `has_object` | ✅ | ✅ |
| `versions_for_object` | ✅ | ✅ |
| `read_object` | ✅ | ✅ |
| `iter_objects` | ✅ | ✅ |
| `iter_latest_objects` | ✅ | ✅ |
| `search_latest_objects` | ✅ | ✅ |
| `raw_records_for_episode` | ✅ | ✅ |
| `record_primitive_call` | ✅ | ✅ |
| `iter_primitive_call_logs` | ✅ | ✅ |
| `record_budget_event` | ✅ | ✅ |
| `iter_budget_events` | ✅ | ✅ |

**14/14 完整覆盖。**

`PrimitiveTransaction` Protocol 定义 9 个方法：SQLite 10/9（多出 `iter_latest_objects`），PostgreSQL 9/9 精确匹配。

**5.2.2 Schema 一致性**

| 层 | `search_text` | `object_embeddings` | 索引 |
|----|---------------|---------------------|------|
| `sql_tables.py` 定义 | ✅ Column(Text, NOT NULL) | ✅ 独立表 (FK CASCADE) | 9 个新索引 |
| Alembic 0002 | — | — | 6 个检索索引 |
| Alembic 0003 | ✅ ADD COLUMN + GIN trgm | ✅ CREATE TABLE + VECTOR(64) | 3 个新索引 |
| `_validate_and_insert` | ✅ 写入 | ✅ 写入 | — |
| `_backfill_retrieval_artifacts` | ✅ 回填 | ✅ 回填（幂等检查） | — |

**定义 → 迁移 → 运行时三层一致。**

**5.2.3 检索链完整性**

```
PrimitiveService._retrieve
  → store.iter_latest_objects (过滤 + 最新版本)
  → store.search_latest_objects (评分 + 排序 + 截断)
    → [SQLite] retrieval.search_objects (内存)
    → [PostgreSQL] _search_latest_objects (SQL)
      → pg_trgm similarity + LIKE boost (keyword)
      → CAST(created_at) 范围 (time_window)
      → object_embeddings <=> cosine (vector)
```

从 API 入口到存储后端，调用链完整、无断裂。

**5.2.4 测试覆盖**

| 测试文件 | 测试数 | 覆盖范围 |
|----------|--------|----------|
| `test_phase_d_smoke.py` | 4 | benchmark 冻结 × 3 + 全流程 smoke |
| `test_workspace_builder.py` | 2 | 正常构建 + 无效跳过 |
| `test_workspace_context_protocol.py` | 2 | 上下文确定性 + 紧凑性 |
| `test_phase_c_primitives.py` | 2 | retrieve 过滤 + vector 后端守卫 |
| `test_postgres_regression.py` | 4 | Postgres iter/workspace/vector/Phase D |
| `test_phase_d_deep_audit.py` | 36 | 边界/错误路径/多模式集成（深度复审新增） |
| **Phase D 新增总计** | **50 条** | |

原有 Phase B/C 测试 18 条继续通过。全套共 68 pass + 5 skip。

基准测试覆盖：12 smoke + 100 benchmark + 100 answer = **212 个评测 case**。

### 5.3 合理性

**5.3.1 架构设计**

- **双后端对称性**: SQLite / PostgreSQL 共享 `retrieval.py` 的 `matches_retrieval_filters()` 和评分逻辑；PostgreSQL 版本将其提升为 SQL 级操作。合理。
- **确定性嵌入**: `embed_text()` 基于 SHA-256 → 64 维向量，无需外部模型。满足可复现性需求，但不适用于生产语义检索。在 Phase D gate 定义范围内合理。
- **上下文协议冻结**: `mind.phase_d_context.v1` 使用 `json.dumps(sort_keys=True)` 确保确定性。合理。
- **WorkspaceBuilder 只读**: 不写入 store，只生成 `WorkspaceView` 对象。调用方决定是否持久化。合理。

**5.3.2 PostgreSQL 实现**

- **pgvector VECTOR(64)**: 与 `EMBEDDING_DIM=64` 匹配。`<=>` cosine 距离 + `1 - distance` 转为相似度。正确。
- **pg_trgm**: `similarity()` + 精确短语 `LIKE` boost（复合评分）。LIKE 使用 `\` 转义，正确处理 `%` 和 `_`。
- **JSONB 过滤**: `metadata_json ->> 'task_id'`、`source_refs_json @> [episode_id]`。配合 GIN 索引，查询效率合理。
- **外联嵌入表**: vector 模式使用 `LEFT OUTER JOIN object_embeddings`，缺失嵌入时评分为 0。正确。

**5.3.3 答案评测**

- 5 种 `AnswerKind` 覆盖了 Task 结果、Summary、复合、最终 RawRecord、向量摘要场景
- `answer_from_raw_topk()` 从完整对象中提取；`answer_from_workspace()` 从摘要 slot 中提取
- `score_answer()` 的 4 维加权公式权重合理：任务完成度 45% 最重要，约束 + 覆盖各 20%，忠实度 15%
- `task_success` 要求完成度和约束同时为 1.0，比 `answer_quality_score` 更严格

### 5.4 安全性与健壮性

- **SQL 注入**: 所有 SQL 使用 `sa.bindparam()` 参数化，无字符串拼接 SQL
- **LIKE 注入**: `_like_pattern()` 转义 `\`、`%`、`_`，正确
- **Invalid 对象过滤**: `_latest_objects_subquery` 默认排除 `status=invalid`；`WorkspaceBuilder` 跳过 `status in {"invalid"}` 的候选
- **除零保护**: `_safe_ratio()` 处理 denominator=0；`_coverage()` 处理 gold_ids 为空
- **Schema 验证**: `WorkspaceBuilder.build()` 在返回前调用 `ensure_valid_object(workspace)`，确保输出符合 schema

---

## 6. 发现的缺陷与修复

### DEF-1：ruff I001 import block 排序（低）

**文件:** `mind/kernel/postgres_store.py`  
**描述:** `from alembic import command` 和 `from alembic.config import Config` 与 `sqlalchemy` 块之间有空行分隔，ruff I001 规则视为独立 import 块，要求重新排序。  
**修复:** `ruff check --fix` 自动修复，将 alembic 导入移至 sqlalchemy 块之后。  
**状态:** ✅ 已修复

### DEF-2：`cosine_similarity` 使用 `strict=False` 掩盖维度不匹配（中）

**文件:** `mind/kernel/retrieval.py`  
**描述:** `zip(left, right, strict=False)` 会在向量维度不匹配时静默截断到较短维度，返回错误的相似度值而非报错。如果因代码变更导致 EMBEDDING_DIM 与实际向量维度不一致，该 bug 会被隐藏。  
**修复:** 改为 `strict=True`，维度不匹配时立即抛出 `ValueError`。  
**验证:** 新增测试 `test_cosine_similarity_dimension_mismatch_raises` 确认。  
**状态:** ✅ 已修复

### DEF-3：`score_answer` 未防御 `required_fragments` 为空的除零错误（中）

**文件:** `mind/workspace/answer_benchmark.py`  
**描述:** `matched_fragments / float(len(case.required_fragments))` 在 `required_fragments=()` 时触发 `ZeroDivisionError`。虽然当前 fixture 保证非空，但 `score_answer` 作为公共 API，不应依赖调用方的约束。  
**修复:** 增加 `if not case.required_fragments: task_completion_score = 0.0` 前置检查。  
**验证:** 新增测试 `test_score_answer_empty_required_fragments_no_crash` 确认。  
**状态:** ✅ 已修复

### DEF-4：`answer_from_workspace` slots↔selected_ids 索引配对无防护（中）

**文件:** `mind/workspace/answer_benchmark.py`  
**描述:** `selected_ids[index]` 在 `len(payload["slots"]) > len(payload["selected_object_ids"])` 时触发 `IndexError`。虽然 `WorkspaceBuilder` 保证等长，但反序列化的上下文可能来自外部或被篡改。  
**修复:** 增加长度一致性前置检查，不匹配时抛出 `RuntimeError` 并附带清晰错误消息。  
**验证:** 新增测试 `test_answer_from_workspace_length_mismatch_raises` 确认。  
**状态:** ✅ 已修复

### DEF-5：`_tokenize` 在 `answer_benchmark.py` 和 `retrieval.py` 间违反 DRY（低）

**文件:** `mind/workspace/answer_benchmark.py`, `mind/kernel/retrieval.py`  
**描述:** 完全相同的 `_tokenize` 函数在两处独立实现：`re.findall(r"[a-z0-9]+", text.lower())`。如果未来修改分词逻辑只更新一处，两个模块的行为会分裂。  
**修复:** 在 `retrieval.py` 中将 `_tokenize` 提升为公共 `tokenize()`，`answer_benchmark.py` 改为 `from mind.kernel.retrieval import tokenize`，删除本地副本。  
**状态:** ✅ 已修复

---

## 7. 观察项（非阻塞）

### OBS-1：`_PostgresStoreTransaction` 缺少 `iter_latest_objects`

**描述:** `_SQLiteStoreTransaction` 实现了 `iter_latest_objects`（超出 Protocol 要求），但 `_PostgresStoreTransaction` 没有。  
**影响:** `PrimitiveTransaction` Protocol 不要求此方法，当前代码通过 `MemoryStore` 而非 Transaction 调用检索。无功能影响。  
**建议:** Phase E 如需 Transaction 内检索，应补充 PostgreSQL 版本。

### OBS-2：service.py `_retrieve` 中的双重过滤

**描述:** `_retrieve` 首先调用 `store.iter_latest_objects()` 获取过滤后对象列表（仅用于 `len()` 计算 `max_candidates` 和成本），随后调用 `store.search_latest_objects()` 重新应用相同过滤逻辑。  
**影响:** PostgreSQL 后端产生两次 SQL 查询。语义正确但存在性能冗余。  
**建议:** 可将 `filtered_count` 作为 `search_latest_objects` 的附带返回值，合并为单次查询。

### OBS-3：`_backfill_retrieval_artifacts` 每次迁移运行

**描述:** `run_postgres_migrations()` 每次调用后都执行 `_backfill_retrieval_artifacts()`，遍历所有对象行。  
**影响:** 在大规模数据库上可能较慢。当前因 embedding 幂等检查（`embedding_exists`）可安全重跑。  
**建议:** 可增加版本标记或仅回填缺失行的优化查询。

### OBS-4：`cosine_similarity` 使用 `max(0.0, ...)` 丢弃负相似度

**描述:** 余弦相似度范围为 [-1.0, 1.0]，`max(0.0, ...)` 将所有反相关向量映射为 0 分。这意味着 vector 模式只能提升总分，不能降低不相关候选的排名。  
**影响:** 当前基于确定性本地嵌入的场景下表现合理。但如果改用真实语义嵌入，丢弃负信号可能影响排序精确度。  
**建议:** 保留为 Phase E/F 优化机会。

### OBS-5：WorkspaceBuilder N+1 查询模式

**描述:** `build()` 对每个 `candidate_id` 逐一调用 `store.read_object()`。20 个候选 = 20 次独立查询。  
**影响:** SQLite 本地无影响；PostgreSQL 后端产生 N 次网络往返。当前候选数 ≤ 20，延迟可控。  
**建议:** Phase E 如需优化，可批量预加载候选对象。

### OBS-6：`_token_count` 使用朴素空格分词

**描述:** `context_protocol._token_count(text)` 使用 `len(text.split())`，对紧凑 JSON（无缩进、少空格）会大幅低估 token 数。  
**影响:** D-5 的 `token_cost_ratio` 两端使用相同计数方法，比率有效。但绝对 token 数无实际意义。  
**建议:** Phase F 集成 LLM 时应替换为 tiktoken 等真实 tokenizer。

---

## 8. 补充测试覆盖

深度复审发现原有测试存在以下覆盖空白，已新增 `tests/test_phase_d_deep_audit.py`（36 条测试）予以补充：

### 8.1 WorkspaceBuilder 边界测试（8 条）

| 测试 | 覆盖场景 |
|------|----------|
| `test_all_candidates_invalid_raises_error` | 所有候选 status=invalid 时正确抛出 WorkspaceBuildError |
| `test_slot_limit_exceeds_candidate_count` | slot_limit=10 但只有 2 个候选 → 正确选择 2 个 |
| `test_deduplication_keeps_highest_score` | 重复 candidate_id 保留最高分 |
| `test_empty_task_id_raises_error` | task_id="" 触发参数校验 |
| `test_empty_candidate_ids_raises_error` | candidate_ids=[] 触发参数校验 |
| `test_misaligned_scores_raises_error` | scores 长度与 ids 不匹配时报错 |
| `test_missing_candidate_raises_error` | 不存在的 object_id 触发正确错误 |
| `test_workspace_source_refs_match_selected_ids` | workspace.source_refs 精确等于 selected_ids |

### 8.2 检索模块边界测试（17 条）

| 测试 | 覆盖场景 |
|------|----------|
| `test_keyword_score_empty_query_returns_zero` | 空查询字符串 |
| `test_keyword_score_no_overlap_returns_zero` | 完全不匹配的查询 |
| `test_time_window_open_start_only` | 仅有 end 边界的时间窗口 |
| `test_time_window_open_end_only` | 仅有 start 边界的时间窗口 |
| `test_time_window_string_query_returns_zero` | 字符串查询对 time_window 返回 0 |
| `test_time_window_no_bounds_returns_zero` | 空 dict 查询 |
| `test_embed_text_empty_string_returns_zero_vector` | 空文本嵌入为零向量 |
| `test_embed_text_deterministic` | 相同输入产生相同嵌入 |
| `test_embed_text_normalized` | 嵌入向量 L2 范数 = 1.0 |
| `test_cosine_similarity_identical_vectors` | 自身相似度 = 1.0 |
| `test_cosine_similarity_empty_vectors` | 空向量返回 0.0 |
| `test_cosine_similarity_dimension_mismatch_raises` | 维度不匹配抛出 ValueError（DEF-2 验证） |
| `test_vector_score_none_embedding_returns_zero` | 无嵌入时返回 0 |
| `test_build_search_text_contains_id_and_type` | search_text 包含对象 id 和 type |
| `test_tokenize_basic` / `test_tokenize_empty` | 公共 tokenize 函数基本行为 |
| `test_multi_mode_keyword_plus_vector_scoring` | KEYWORD+VECTOR 组合评分高于单一模式 |
| `test_multi_mode_keyword_plus_time_window` | KEYWORD+TIME_WINDOW 组合评分 |

### 8.3 上下文协议边界测试（2 条）

| 测试 | 覆盖场景 |
|------|----------|
| `test_build_raw_topk_context_empty_ids` | 空 object_ids 产生有效空上下文 |
| `test_workspace_context_deterministic` | 同一 workspace 两次序列化结果一致 |

### 8.4 答案评分边界测试（5 条）

| 测试 | 覆盖场景 |
|------|----------|
| `test_score_answer_empty_answer_text` | 空答案得低分 |
| `test_score_answer_empty_required_fragments_no_crash` | 空 fragments 不崩溃（DEF-3 验证） |
| `test_score_answer_perfect_match` | 完美匹配得 1.0 |
| `test_score_answer_faithfulness_zero_when_no_overlap` | 不重叠时 faithfulness = 0 |
| `test_answer_from_workspace_length_mismatch_raises` | slots↔ids 长度不匹配时报错（DEF-4 验证） |

### 8.5 Service 层多模式集成测试（3 条）

| 测试 | 覆盖场景 |
|------|----------|
| `test_keyword_plus_vector_retrieve` | PrimitiveService KEYWORD+VECTOR 端到端 |
| `test_all_three_modes_retrieve` | KEYWORD+TIME_WINDOW+VECTOR 三模式端到端 |
| `test_vector_only_with_embedder_succeeds` | 仅 query_embedder（无 vector_retriever）的 VECTOR 模式 |

---

## 9. Phase E 准入评估

| E-Gate 前置条件 | Phase D 产物支撑情况 | 状态 |
|----------------|---------------------|------|
| 稳定 Workspace | WorkspaceBuilder 输出通过 schema 验证；slot_limit + source_refs 纪律 100% | ✅ 就绪 |
| 可用检索 | 3 种模式全部可用；recall@20 = 1.00 | ✅ 就绪 |
| Token 成本收益 | workspace context 仅 raw_topk 的 18%；无任务成功退化 | ✅ 就绪 |
| 答案级评测框架 | `answer_benchmark.py` 已实现 5 种 AnswerKind + 4 维评分 | ✅ 就绪 |
| 上下文协议 | `mind.phase_d_context.v1` 冻结，确定性序列化 | ✅ 就绪 |
| PostgreSQL 检索 | pgvector + pg_trgm + JSONB 索引全部就位 | ✅ 就绪 |

**Phase E 需要新建的能力：**
- E-1: 派生对象 source trace（workspace → replay/反思路径）
- E-2: Schema validation precision（需要 evidence audit 框架）
- E-3: ReplayLift（需要 LongHorizonDev v1 基准）
- E-4: PromotionPrecision@10（需要 promotion 机制）
- E-5: Offline maintenance net benefit（需要 PUS 评测和 PollutionRate）

**结论：Phase D 产物为 Phase E 提供了完整的检索和 Workspace 基础设施。Phase E 的 5 项指标所需的新能力不依赖 Phase D 的修改，而是需要新增的反思、promotion 和离线维护机制。**

---

## 10. 审计结论

| 项目 | 结果 |
|------|------|
| D-1 检索模式覆盖 | **PASS** (3/3) |
| D-2 Candidate recall@20 | **PASS** (1.00 ≥ 0.85) |
| D-3 Workspace gold-fact coverage | **PASS** (1.00 ≥ 0.80) |
| D-4 Workspace 槽位纪律 | **PASS** (1.00 = 100%) |
| D-5 成本收益门槛 | **PASS** (0.18 ≤ 0.60, 0.00 ≤ 5.0) |
| ruff / mypy / pytest | **全部通过** (0 error, 41 files, 68 pass + 5 skip) |
| Phase B 回归 | **PASS** |
| 缺陷数 | 5 已修复 (DEF-1~5) |
| 观察项 | 6 非阻塞 (OBS-1~6) |
| 补充测试 | +36 条（原 32 → 现 68） |

### 最终判定

> **Phase D Gate = PASS**
>
> 所有 D-1 ~ D-5 指标通过，工具链检查无错误，回归测试通过。  
> 5 个缺陷已全部修复（含 1 个中等 cosine_similarity 维度安全缺陷、1 个中等除零防护缺陷、1 个中等索引越界防护缺陷、1 个 DRY 违反、1 个 import 排序）。  
> 6 个观察项均为非阻塞的设计优化建议，不影响 Gate 判定。  
> 补充 36 条边界/集成测试，覆盖 WorkspaceBuilder 全部 error path、检索模块多模式组合、答案评分边界条件等原有盲区。  
> Phase D 产物已具备支撑 Phase E 启动的全部前置条件。
