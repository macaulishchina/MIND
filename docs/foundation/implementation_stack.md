# MIND 实现技术栈冻结文档

冻结日期：`2026-03-08`
最近更新：`2026-03-09`

适用范围：

- Phase B 基线原型
- Phase C Primitive API
- Phase D Retrieval / Workspace
- Phase E 离线维护与轻量重组
- Phase F / G 评测、优化与部署演进

相关文档：

- 语义与对象/primitive 定义见 [spec.md](./spec.md)
- 阶段 gate 与验收标准见 [phase_gates.md](./phase_gates.md)
- 实施拆解见 [design_breakdown.md](../design/design_breakdown.md)

本文目的：

- 冻结实现层的主技术栈
- 明确哪些技术已经选定，哪些只在后续阶段启用
- 明确哪些技术当前不应引入，避免工程复杂度失控

## 1. 冻结原则

1. 语义先于实现。对象模型、primitive contract、workspace contract 以 [spec.md](./spec.md) 为准，技术栈只能服务这些语义，不反向改写语义。
2. 单体优先于分布式。Phase B ~ E 以单代码库、单后端服务、单主数据库为默认形态，不预设微服务。
3. 主库唯一真相源。所有对象版本、primitive 调用日志、评测结果都必须回到同一真相源，不允许 Redis 或向量库成为事实源。
4. 分阶段引入复杂度。只有当阶段 gate 或 profiling 明确证明需要时，才引入新的基础设施。
5. 库优先、服务其次。核心能力先以 Python library 形式稳定，再决定是否暴露 HTTP API。
6. 最少依赖。优先选择少而强的基础组件，避免同时引入功能重叠的框架。

## 2. 总体冻结结果

| 层 | 冻结选型 | 状态 | 说明 |
| --- | --- | --- | --- |
| 核心实现语言 | `Python 3.12` | 已冻结 | 作为 Phase B 之后的主实现语言 |
| 项目配置与依赖管理 | `pyproject.toml` + `uv` | 已冻结 | 后续依赖、脚本、锁文件统一走这一套 |
| 数据模型校验 | `Pydantic v2` | 已冻结 | 对象 validator 仍保留手写实现；primitive request / response 已转为显式 typed models |
| SQL 访问层 | `SQLAlchemy 2 Core` + `psycopg 3` | 已冻结 | 只用 Core，不采用 ORM domain mapping |
| 数据库迁移 | `Alembic` | 已冻结 | Postgres 阶段的 schema 变更必须走 migration |
| 本地最小存储 | `SQLite` | 已冻结 | Phase B / C 基线、CI、gate 与 parity 校验 |
| 正式主存储 | `PostgreSQL 16` + `JSONB` | 已冻结 | Phase D 起的默认真相源 |
| 向量检索 | `pgvector` | 已冻结 | 不单独引入向量数据库 |
| 关键词检索 | `pg_trgm` 为主，`Postgres FTS` 为辅 | 已冻结 | 兼顾中文/多语言和结构化过滤 |
| 缓存 / 分布式锁 | `Redis 7` | 条件启用 | 只在 Phase D/E 之后按需启用，不做真相源 |
| 大对象存储 | 本地文件系统开发态，`S3-compatible` 部署态 | 已冻结 | 大附件不直接塞主表 |
| HTTP API | `FastAPI` | 已冻结 | 服务化时的默认 API 框架 |
| HTTP 客户端 | `httpx` | 已冻结 | 用于 LLM/embedding/provider 调用 |
| 测试主框架 | `pytest` | 已冻结 | 现有 `unittest` 测试允许过渡期继续存在 |
| 格式化 / lint | `ruff format` + `ruff check` | 已冻结 | 不再引入 Black + Flake8 双栈 |
| 类型检查 | `mypy` | 已冻结 | 核心模块逐步提升到严格模式 |
| 结构化日志 | Python `logging` + JSON formatter | 已冻结 | 不强制引入重型日志框架 |
| 指标 / tracing | `Prometheus-compatible metrics` + `OpenTelemetry` | 后期启用 | Phase F/G 才成为强约束 |
| 本地编排 | `docker compose` | 已冻结 | 用于 Postgres / Redis / MinIO 本地联调 |
| 部署形态 | 单 API 服务 + 单 worker + 单 Postgres | 已冻结 | 初期不做 Kubernetes / 微服务 |

## 3. 分阶段技术选型

### 3.1 Phase B：最小记忆内核

目标：

- 正确性优先
- append-only / replay / integrity 优先
- 不引入不必要的外部依赖

冻结方案：

- 语言：`Python 3.12`
- 存储：`SQLite`
- 校验：当前可接受手写 validator，后续迁移到 `Pydantic v2`
- 测试：现有 `unittest` 基线可保留
- 运行方式：脚本 + 本地库调用

说明：

- 当前仓库中的 [store.py](../../mind/kernel/store.py) 采用 `sqlite3` 标准库实现，这符合 Phase B 的正确性基线目标。
- Phase B 不要求并发写入、服务化部署、远程 API，也不要求 Redis、Postgres、对象存储。

当前状态：

- Phase B 已于 `2026-03-08` 通过验收，详见 [Phase B 验收报告](../reports/phase_b_acceptance_report.md)。
- 当前实现包含 [schema.py](../../mind/kernel/schema.py)、[store.py](../../mind/kernel/store.py)、[integrity.py](../../mind/kernel/integrity.py)、[replay.py](../../mind/kernel/replay.py) 和 [golden_episode_set.py](../../mind/fixtures/golden_episode_set.py)。

### 3.2 Phase C：Primitive API

目标：

- 让 `7` 个 primitives 成为稳定接口
- 强化 request / response schema
- 增加结构化日志、预算控制、失败原子性

冻结方案：

- 保留 `Python 3.12`
- 存储仍使用 `SQLite`，Phase C gate 不依赖 PostgreSQL
- 引入 `Pydantic v2` 定义 primitive request / response models
- 引入 `pytest` 作为标准测试入口
- 建立 `pyproject.toml` + `uv` 项目结构
- 建立最小 `MemoryStore` 抽象层（接口与 SQLite 实现分离），为 Phase D 迁移做准备

说明：

- Phase C 的核心是把 primitive contract 冻结下来，不是做基础设施迁移。
- Phase C gate（C-1 ~ C-5）全部可在 SQLite 上验证，无需提前引入 PostgreSQL。
- `MemoryStore` 抽象是 Phase C 的必做项，因为 primitive 一旦直接绑定到 SQLite 细节，Phase D 的主存储迁移就会变成接口重写，而不是 backend 替换。
- `FastAPI` 在此阶段不引入；primitive 的第一公民形态是库函数，服务化暴露推迟到 Phase D/E，符合"库优先、服务其次"原则。
- PostgreSQL、SQLAlchemy、Alembic 统一推迟到 Phase D，与检索基础设施一起引入，符合"分阶段引入复杂度"原则。

当前状态：

- `pyproject.toml`、`uv`、`pytest`、`ruff`、`mypy` 已建立并成为默认工程入口
- primitive contract、runtime、service object 和 Phase C gate 已落地
- `PrimitiveGoldenCalls v1` 已建立，`C-1 ~ C-5` 可在 SQLite 基线上直接验证

### 3.3 Phase D：Retrieval / Workspace

目标：

- 完成从 SQLite 到 PostgreSQL 的主存储迁移
- 支持 `keyword / vector / time-window` 三类检索
- WorkspaceView builder 可控、可审计、可评测

冻结方案：

- 主库迁移至 `PostgreSQL 16`
- SQL 层采用 `SQLAlchemy 2 Core` + `psycopg 3`
- schema migration 采用 `Alembic`
- 关键词检索：`pg_trgm`
- 可选补充：`Postgres FTS`
- 向量检索：`pgvector`
- 时间窗口检索：Postgres 时间索引 + 必要的表达式索引
- 缓存：`Redis 7` 可按需启用，用于热结果缓存、分布式锁、短 TTL workspace 副本
- 如需服务化，外部 API 框架使用 `FastAPI`

说明：

- Phase D 是 PostgreSQL 迁移的自然触发点：`pgvector` 和 `pg_trgm` 要求 Postgres，将存储迁移与检索引入合并到同一阶段可减少集成风险。
- 对中文、多语言和半结构文本，`pg_trgm` 比单纯依赖英文导向的 FTS 更稳妥，因此将其冻结为关键词检索的主路径。
- `pgvector` 与 `Postgres` 同库共存，避免早期引入独立向量数据库带来的同步、权限、备份和一致性复杂度。
- Phase D 之后的运行口径不是“双主库存储并存”，而是“`PostgreSQL` 作为正式主存储，`SQLite` 作为参考/测试后端保留”。
- PostgreSQL backend 切换完成后，必须在新 backend 上重新执行 Phase B 的核心不变量检查，至少包括 round-trip、replay fidelity、source trace coverage 和 version integrity。

当前状态：

- PostgreSQL backend、Alembic migration、Retrieval v1、Workspace builder v1 已落地。
- 当前仓库已建立 `RetrievalBenchmark v1`、`EpisodeAnswerBench v1`、本地 `Phase D smoke`、冻结的 `raw-top20 / workspace` context protocol，以及 answer-level `D-5` A/B benchmark。
- 当前工作树已经通过本地 `Phase D acceptance gate`；正式口径见 [phase_d_acceptance_report.md](../reports/phase_d_acceptance_report.md)。
- Phase D 之后的剩余工作不再是“补齐 D-5”，而是进入独立审计与 Phase E 的长期维护闭环。

### 3.4 Phase E：离线维护 / 反思 / 重组

目标：

- 支持 replay、reflect、schema promotion、轻量维护作业
- 将在线请求路径与离线维护路径分开

冻结方案：

- 仍保持单代码库
- 增加独立 worker 进程，但不拆微服务
- 作业调度优先采用 `Postgres jobs table + advisory locks`
- 若缓存 / 锁 / 异步任务压力升高，再引入 `Redis`
- 大对象落地到 `S3-compatible storage`

说明：

- Phase E 不引入 `Celery`、`Kafka`、`Airflow` 这类重型系统。
- 优先用数据库表驱动的轻量作业模型，保证 traceability 和调试简单性。

当前状态：

- 当前仓库已经落地 `offline_jobs`、`OfflineWorker.run_once(...)`、`OfflineMaintenanceService`、promotion policy、`LongHorizonDev v1` 和 formal `Phase E gate`。
- PostgreSQL claim 路径已采用 `FOR UPDATE SKIP LOCKED + advisory lock` 的最小实现，并已接入 Phase E regression 路径。
- Phase E 已完成本地验收与独立审计；Phase F 已完成本地验收与独立审计；Phase G 已完成本地验收与独立审计。

### 3.5 Phase F / G：评测、优化、部署演进

目标：

- 完成 benchmark、成本审计、长程 utility 优化
- 在更稳定的服务形态下运行

冻结方案：

- API 仍为 `FastAPI`
- 部署为“单 API 服务 + 单 worker + 单 Postgres + 可选 Redis + 可选 S3”
- 指标导出采用 `Prometheus-compatible metrics`
- tracing 采用 `OpenTelemetry`
- 本地 / 测试 / staging 的基础设施统一用 `docker compose`

说明：

- 在没有真实负载证据前，不进入 Kubernetes、多 region、多数据库拆分等复杂形态。
- 优化优先从算法、索引、查询计划、prompt/context 成本入手，而不是过早切到多语言多服务架构。

## 4. 语言与运行时

### 4.1 主语言

冻结结论：

- 主语言为 `Python 3.12`

理由：

- 适合快速迭代 retrieval、workspace、evaluation、LLM integration
- 类型系统、数据处理、测试生态足够成熟
- 与主流模型/embedding/provider SDK 兼容性最好

约束：

- 核心内核代码必须有类型注解
- 默认使用同步代码实现核心 store / validator / replay
- 只有在 provider IO 或服务层确有必要时才使用 async

补充：

- `3.12` 是冻结的最低版本，兼容 `3.13+`；但不主动依赖 `3.13` 专有特性，以保持向下兼容。

### 4.2 不冻结为主语言的选项

- `TypeScript / Node.js`：不作为核心后端语言，只可用于未来独立前端或可视化工具
- `Go`：当前不作为主语言，除非后期 profiling 证明某些服务边界需要高并发独立组件
- `Rust`：不作为 Phase B ~ G 的默认实现语言，只能在明确热点路径上局部引入

## 5. 依赖与项目工具链

### 5.1 项目配置

冻结结论：

- 用 `pyproject.toml` 作为单一项目配置入口
- 用 `uv` 管理虚拟环境、依赖安装、锁文件与命令执行

约束：

- 依赖版本以 lockfile 为准，文档只冻结主技术和 major line
- 不同时维护 `requirements.txt`、`poetry.lock`、`pipenv` 三套系统

当前状态：

- `pyproject.toml` 已建立，`uv` 负责依赖、虚拟环境和脚本入口。
- 当前默认开发入口包括 `uv run pytest`、`uv run mindtest-phase-b-gate`、`uv run mindtest-phase-c-gate`。

### 5.2 代码质量工具

冻结结论：

- 格式化：`ruff format`
- lint：`ruff check`
- 类型检查：`mypy`
- 测试：`pytest`

说明：

- 现有 Phase B 测试仍可暂时保留 `unittest.TestCase`
- 从 Phase C 开始，新测试默认按 `pytest` 编写

## 6. 数据层与持久化

### 6.1 总体策略

冻结结论：

- `PostgreSQL 16` 是正式主存储（Phase D 起）
- `SQLite` 保留为 Phase B / C 基线、CI 与测试后端
- Redis 不作为主存储

进一步说明：

- `SQLite` 和 `PostgreSQL` 不是两个正式主存储；项目只有一个正式真相源，即 `PostgreSQL`。
- `SQLite` 保留的目的，是提供一个低依赖、快启动、确定性的 reference backend，用于 Phase B / C 基线、单元测试、CI、gate 和 parity 校验。
- 新的正式能力以 `PostgreSQL` 为准，尤其是依赖 `JSONB`、`pg_trgm`、`pgvector`、Alembic migration、真实事务与索引能力的部分。
- `SQLite` 继续存在，是为了验证上层 `MemoryStore` 语义没有漂移，而不是为了长期双写、双活或双真相源。
- 一旦某项能力明显依赖 PostgreSQL 特性，不要求 `SQLite` 与其完全等价；此时 `SQLite` 只需继续承担最小语义基线与回归检查职责。

### 6.2 数据建模原则

冻结结论：

- 核心对象继续采用统一对象表，而不是按 `8` 类对象拆成 `8` 张业务表
- 通用字段单独建列
- `content` 与 `metadata` 使用 `JSONB`
- 版本采用 append-only，不做 in-place overwrite

编码说明：

- Phase B / C 的 SQLite 实现可以继续使用当前 JSON 序列化策略，但这只是本地存储细节，不应被视为语义 contract。
- replay 与评测所依赖的 hash 确定性，必须来自 replay / evaluation 层的 canonical serialization，而不是来自数据库内部 JSON 的编码形式。
- 迁移至 PostgreSQL `JSONB` 后，应使用原生 Unicode 存储，不再围绕 `ensure_ascii` 设计语义约束。

建议的核心表：

- `object_versions`
  - 真相源表
  - 按 `(object_id, version)` 唯一
  - 包含 `type / created_at / updated_at / status / priority / content_jsonb / metadata_jsonb`
- `primitive_call_logs`
  - 记录 primitive request / response / actor / outcome / cost / target_ids
- `object_embeddings`
  - 存储可检索对象的 embedding 向量及 embedding model 标识
- `maintenance_jobs`
  - 记录离线作业、重放、反思、promotion 和清理任务

可选派生结构：

- `latest_object_versions` 视图或物化视图
- 针对常用过滤条件的表达式索引
- 针对 `episode_id`、`task_id` 等高频元数据的提升列或生成列

### 6.3 SQL 访问层

冻结结论：

- 使用 `SQLAlchemy 2 Core`
- 驱动使用 `psycopg 3`
- migration 使用 `Alembic`

明确不采用：

- 不采用 SQLAlchemy ORM 的重度实体映射作为核心对象层
- 不采用隐藏 SQL 细节的仓储框架

理由：

- MIND 的核心对象是“统一 schema + 异构内容”，更适合显式 SQL 和 JSONB，而不是复杂 ORM 关系映射。

### 6.4 并发与事务

冻结结论：

- primitive 写操作必须包在数据库事务中
- 默认隔离级别采用 `READ COMMITTED`
- 版本链分配、离线作业认领、关键维护路径使用行锁或 advisory locks

说明：

- Phase B 的 SQLite 基线不强调高并发
- 从 Postgres 阶段开始，必须避免多个 primitive 并发写入导致版本错乱

## 7. 检索层

### 7.1 关键词检索

冻结结论：

- 主路径：`pg_trgm`
- 辅助路径：`Postgres FTS`

理由：

- `pg_trgm` 对中文、多语言、别名、模糊匹配更稳妥
- FTS 可以作为英文或分词良好文本的加速层

### 7.2 向量检索

冻结结论：

- 使用 `pgvector`

约束：

- 向量索引对象必须能回指到对象版本或最新版本
- embedding model 版本必须写入元数据或 side table
- 向量索引是派生结构，不是真相源

### 7.3 时间窗口检索

冻结结论：

- 直接使用 Postgres 时间字段索引实现

说明：

- 高频过滤条件不应全部埋在 `JSONB` 深处
- 对确实高频的时间、episode、task 维度，应提升为索引友好的列或表达式索引

## 8. API 与服务化

### 8.1 接口策略

冻结结论：

- 内部以 Python library API 为主
- 外部以 `FastAPI` HTTP API 为辅

说明：

- primitive 的第一公民形态是库函数 / service object，而不是 HTTP route
- HTTP 层用于远程调用、集成测试、外部系统接入

### 8.2 请求响应模型

冻结结论：

- 所有 primitive request / response、retrieval query、workspace builder input/output 都用 `Pydantic v2` 显式建模

约束：

- 禁止使用无 schema 的裸 `dict` 作为长期 API contract
- 错误码、预算错误、部分失败、回滚失败都要显式化

## 9. LLM / Embedding / Provider 集成

### 9.1 冻结内容

- provider 调用通过独立 adapter 层封装
- HTTP 客户端统一用 `httpx`
- generation 与 embedding client 分开抽象
- prompt / tool / model routing 不依赖 LangChain、LlamaIndex 这类重型编排框架

### 9.2 不冻结为具体厂商

- 不冻结单一 LLM vendor
- 不冻结单一 embedding vendor
- 不冻结单一 reranker vendor

说明：

- 研究系统要能在不同 provider 间切换
- 真正需要冻结的是“内部调用接口”，而不是外部供应商名字

## 10. 缓存、队列与后台任务

### 10.1 缓存

冻结结论：

- `Redis 7` 仅作为可选缓存层

缓存适用对象：

- 热门 retrieval 结果
- 临时 workspace 副本
- 短 TTL rerank 结果
- 分布式锁

禁止事项：

- 不把对象真相数据只写 Redis
- 不把 append-only version history 建在 Redis

### 10.2 后台任务

冻结结论：

- Phase E 前优先采用“同代码库 worker + Postgres jobs table”

明确不采用：

- 不默认引入 `Celery`
- 不默认引入 `Kafka`
- 不默认引入 `Airflow`

理由：

- 这些系统对当前规模来说运维成本过高，且会模糊 traceability

## 11. 大对象与附件

冻结结论：

- 小对象直接存主库
- 大日志、大工具结果、附件、文件类 payload 存对象存储

开发态：

- 本地文件系统目录

部署态：

- `S3-compatible storage`

约束：

- 主库只存引用、摘要、校验和、媒体类型和大小信息

## 12. 可观测性与审计

### 12.1 日志

冻结结论：

- 统一使用 Python `logging`
- 输出结构化 JSON 日志

必须记录的字段：

- `timestamp`
- `actor`
- `primitive`
- `target_ids`
- `episode_id`
- `task_id`
- `cost`
- `outcome`
- `latency_ms`

### 12.2 指标与 tracing

冻结结论：

- 服务化部署后导出 `Prometheus-compatible metrics`
- Phase F / G 开始引入 `OpenTelemetry`

说明：

- B ~ E 阶段主要靠结构化日志和离线评测
- F / G 阶段再强化在线指标与 tracing

## 13. 测试、评测与 CI

冻结结论：

- 单元测试、contract tests、benchmark eval 同在 Python 体系内完成
- `pytest` 是统一测试入口
- gate 脚本继续作为可直接运行的 CLI 验收入口

测试类型：

- 单元测试
- schema / contract tests
- rollback / fault injection tests
- replay / integrity tests
- retrieval benchmark tests
- utility / cost evaluation

CI 原则：

- 先跑 lint / type check / unit tests
- 再跑 phase gate 脚本
- benchmark 类任务可拆成较慢的独立 job

## 14. 本地开发与部署

### 14.1 本地开发

冻结结论：

- Phase B 可直接使用本机 Python + SQLite
- Postgres / Redis / MinIO 联调用 `docker compose`

### 14.2 初期部署

冻结结论：

- 单 API 服务
- 单 worker
- 单 Postgres
- 可选 Redis
- 可选 S3-compatible storage

明确不采用：

- 初期不做 Kubernetes
- 初期不做 service mesh
- 初期不做多数据库拆分

## 15. 安全与配置管理

冻结结论：

- 配置来源以环境变量为主
- 本地脚本默认使用按环境拆分的运行时文件：`.env.dev.local` / `.env.prod.local`
- 使用 typed settings 模型统一读取配置

约束：

- secrets 不写入仓库
- 数据库和对象存储凭证必须走环境变量或安全注入
- 评测数据与生产用户数据必须逻辑隔离

## 16. 明确不采用或暂不采用的技术

以下技术当前明确不进入主栈：

- 图数据库作为主存储
- 独立向量数据库作为 Phase D 之前的默认方案
- Redis 作为主库
- LangChain / LlamaIndex 作为核心业务编排框架
- 微服务拆分
- Celery / Kafka / Airflow 作为默认后台任务基础设施
- Kubernetes 作为初期部署目标
- 多语言混合后端作为常态

## 17. 重新评估触发条件

只有出现以下情况之一，才应重新审查本技术栈：

1. Phase gate 明确无法达标，且根因已确认是基础设施而非算法问题。
2. 单库 Postgres 在真实负载下成为主要瓶颈，并经过 profiling 证实无法通过索引、缓存、查询优化解决。
3. 离线维护吞吐明显高于在线服务吞吐，且单 worker 模式无法满足时效要求。
4. 多团队并行开发导致单体服务的发布节奏成为核心阻塞。
5. 外部模型或 embedding provider 的协议变化，迫使 adapter 层重构。

## 18. 最终冻结结论

MIND 在当前阶段的正式实现技术栈应理解为：

- 核心语言：`Python 3.12`
- 测试 / reference backend：`SQLite`
- 产品 / 运行时后端：`PostgreSQL 16 + JSONB + pgvector + pg_trgm`
- 外部 API 框架：`FastAPI`（需要服务化时启用）
- 数据模型：`Pydantic v2`
- SQL 层：`SQLAlchemy 2 Core + psycopg 3 + Alembic`
- 测试：`pytest`
- 工具链：`uv + ruff + mypy`
- 缓存：`Redis 7` 可选
- 大对象：`S3-compatible storage` 可选
- 部署：单服务 / 单 worker / 单主库

这是一个以“逻辑边界清晰、依赖适度、便于算法迭代”为目标冻结的技术栈，而不是以“服务数量多、基础设施先进”为目标的技术栈。
