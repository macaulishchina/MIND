# 产品化方案与验收蓝图

这份文档不替代现有 Phase B ~ J 的历史验收记录。

它的作用只有一个：

**把 MIND 从“已通过本地 gate 的研究原型”推进成“可部署、可接入、可直接使用的产品系统”。**

补充约束：

- 历史 `Phase J` 形成的统一开发/验收 CLI 基线继续有效
- 但从产品化开始，开发/验收 CLI 的命名必须迁移到 `mindtest`
- `mind` 这个命名保留给产品级 CLI
- 产品化工作默认建立在 `PostgreSQL` 真相源之上；`SQLite` 仅保留为 reference backend、测试和低成本原型

---

## 实施状态（2026-03-10）

截至 `2026-03-10`，本轮产品化范围已经完成到 `WP-6`：

- `WP-0 ~ WP-6`：已实现并进入仓库基线
- `WP-7 / WP-8`：保留为后续阶段，不属于本轮交付范围
- `mindtest` / `mind` 已分离；`mind/app` 已成为产品边界；`REST API`、`MCP`、产品 CLI 与部署资产均已落地
- 最终验收口径为：新增 `WP-0 ~ WP-6` 测试与历史 `Phase B ~ J` 回归一并通过

---

## 1. 产品化目标

产品化后的 MIND 至少要满足：

1. 可以作为一个完整服务部署，而不只是本地库调用
2. 可以通过统一应用服务层被 `REST API`、`MCP`、产品 CLI 和前端复用
3. 可以管理用户、租户、会话、命名空间和默认执行策略
4. 可以稳定切换 provider / model / endpoint，并保留 deterministic fallback
5. 可以在开发模式下暴露完备内部观测，为调试和可视化提供数据底座

---

## 2. 当前项目整体评估

当前项目已经具备这些强基础：

1. 核心记忆对象、primitive、retrieval、workspace、offline maintenance、governance foundation 都已具备 typed contract
2. `PrimitiveService`、`AccessService`、`GovernanceService`、`OfflineMaintenanceService` 已经形成库优先的领域能力面
3. `PostgreSQL` 存储、Alembic migration、Phase H / I / J formal gate 已经落地

产品化起点的主要缺口曾经是：

1. 缺少统一应用服务层，外部调用方仍需要直接拼装内部 service object
2. 缺少正式的用户状态 / 会话状态 / 执行策略模型
3. 缺少真正的 `REST API`、`MCP server` 和部署资产
4. 缺少产品 CLI；现有 `mind` CLI 实际上是开发/验收总控台
5. 缺少 provider capability layer、产品级 secret/config、运维拓扑与健康检查

截至 `2026-03-10`，其中 `WP-0 ~ WP-6` 范围内的缺口已经完成收口；provider / telemetry 相关能力继续留在后续阶段。

---

## 3. 目标架构

产品化后的系统分为 5 层：

### 3.1 Core Domain

保持现有模块职责：

- `kernel`
- `primitives`
- `access`
- `offline`
- `governance`

这一层继续负责记忆语义与内部正确性，不直接暴露给最终用户。

### 3.2 Application Service Layer

新增统一应用服务层，作为所有对外入口的唯一业务边界。

建议目录：

- `mind/app/contracts.py`
- `mind/app/context.py`
- `mind/app/errors.py`
- `mind/app/services/ingest.py`
- `mind/app/services/query.py`
- `mind/app/services/access.py`
- `mind/app/services/governance.py`
- `mind/app/services/jobs.py`
- `mind/app/services/user_state.py`
- `mind/app/services/system.py`

统一原则：

- 所有产品级动作必须先映射到应用服务
- 所有 transport 只调用应用服务，不直接碰 `MemoryStore` 或内部 service object
- 所有应用服务统一使用显式 request / response envelope
- 所有应用服务统一使用显式 error code、request id、idempotency key、trace ref

### 3.3 Transport Layer

在应用服务层之上提供 3 类正式接入：

1. `REST API`
2. `MCP server`
3. 产品 CLI `mind`

此外保留开发/验收 CLI：

4. `mindtest`

### 3.4 Capability / Provider Layer

统一封装：

- generation
- embedding
- rerank
- moderation

要求：

- 兼容 `openai / claude / gemini`
- provider 差异不能泄露到上层业务 contract
- deterministic baseline 必须作为 fallback 保留

### 3.5 Telemetry / Visualization Layer

为开发态和未来前端 debug 提供：

- internal event stream
- object delta log
- correlation id chain
- trace aggregation

---

## 4. 产品级对象与上下文

### 4.1 必须新增的产品上下文

产品化后，调用前必须能形成以下上下文，而不是只靠 provenance 补字段：

1. `PrincipalContext`
2. `NamespaceContext`
3. `SessionContext`
4. `ExecutionPolicy`
5. `ProviderSelection`

### 4.2 建议字段

#### `PrincipalContext`

- `principal_id`
- `principal_kind`
- `tenant_id`
- `user_id`
- `roles`
- `capabilities`

#### `NamespaceContext`

- `namespace_id`
- `tenant_id`
- `project_id`
- `workspace_id`
- `memory_visibility_policy`

#### `SessionContext`

- `session_id`
- `conversation_id`
- `channel`
- `client_id`
- `device_id`
- `request_id`

#### `ExecutionPolicy`

- `default_access_mode`
- `budget_limit`
- `retention_class`
- `dev_mode`
- `conceal_visibility`
- `fallback_policy`

#### `ProviderSelection`

- `provider`
- `model`
- `endpoint`
- `timeout_ms`
- `retry_policy`

### 4.3 与 provenance 的边界

冻结结论：

- `PrincipalContext / SessionContext / NamespaceContext` 属于产品态执行上下文
- provenance 仍然属于 control plane
- provenance 可以从产品上下文投影，但不能替代产品上下文

---

## 5. 统一应用服务接口

### 5.1 基础 envelope

所有应用服务都统一使用：

- `request_id`
- `idempotency_key`
- `principal`
- `namespace`
- `session`
- `policy`
- `input`

响应统一返回：

- `status`
- `result`
- `error`
- `trace_ref`
- `audit_ref`

### 5.2 最小应用服务面

#### `MemoryIngestService`

负责：

- `remember`
- `import_raw`
- `append_turn`

#### `MemoryQueryService`

负责：

- `get_memory`
- `list_memories`
- `recall`
- `search`

#### `MemoryAccessService`

负责：

- `ask`
- `run_access`
- `explain_access`

#### `GovernanceAppService`

负责：

- `plan_conceal`
- `preview_conceal`
- `execute_conceal`
- 后续 `erase / reshape`

#### `OfflineJobAppService`

负责：

- `submit_job`
- `get_job`
- `list_jobs`
- `cancel_job`

#### `UserStateService`

负责：

- `resolve_principal`
- `open_session`
- `get_session`
- `update_user_preferences`
- `get_runtime_defaults`

#### `SystemStatusService`

负责：

- `health`
- `readiness`
- `config_summary`
- `provider_status`

---

## 6. Transport 设计

### 6.1 REST API

建议最小资源面：

- `POST /v1/memories:remember`
- `POST /v1/memories:recall`
- `POST /v1/memories:ask`
- `POST /v1/memories:search`
- `GET /v1/memories/{id}`
- `GET /v1/memories`
- `POST /v1/governance/conceal:plan`
- `POST /v1/governance/conceal:preview`
- `POST /v1/governance/conceal:execute`
- `POST /v1/jobs`
- `GET /v1/jobs/{id}`
- `GET /v1/jobs`
- `POST /v1/sessions`
- `GET /v1/sessions/{id}`
- `GET /v1/users/me`
- `GET /v1/system/health`
- `GET /v1/system/readiness`
- `GET /v1/system/config`

约束：

- 必须版本化
- 必须有统一错误响应
- 必须支持分页、过滤、排序
- 必须支持 correlation id
- 必须有认证机制（至少支持 API key；后续可扩展 OAuth / JWT）

### 6.2 MCP Server

建议最小 tool 面：

- `remember`
- `recall`
- `ask_memory`
- `get_memory`
- `list_memories`
- `search_memories`
- `plan_conceal`
- `preview_conceal`
- `execute_conceal`
- `submit_offline_job`
- `get_job_status`

约束：

- MCP session 必须映射到 `SessionContext`
- tool 调用必须复用应用服务层
- tool 返回必须与 REST 语义一致，而不是重新发明结构

### 6.3 CLI

#### `mindtest`

保留开发/验收用途：

- `primitive`
- `access`
- `offline`
- `governance`
- `gate`
- `report`
- `demo`
- `config`

#### `mind`

产品级 CLI 仅暴露高层动作：

- `mind remember`
- `mind recall`
- `mind ask`
- `mind history`
- `mind session`
- `mind status`
- `mind config`

约束：

- `mind` 不直接暴露 phase、gate、fixture、demo 等开发语义
- `mind` 必须优先复用应用服务，可本地 in-process，也可远程调用 REST API
- `mindtest` 可以继续保留研究/验收命令，但不得继续占用产品命名空间

---

## 7. 部署方案

### 7.1 最小 compose 拓扑

本地联调 / 初期部署至少包含：

- `postgres`
- `api`
- `worker`

按需启用：

- `redis`
- `minio`
- `otel-collector`
- `frontend`

### 7.2 必备文件

- `compose.yaml`
- `Dockerfile.api`
- `Dockerfile.worker`
- `.env.example`
- `scripts/entrypoint_api.sh`
- `scripts/entrypoint_worker.sh`

### 7.3 环境变量

必备：

- `MIND_POSTGRES_DSN`
- `MIND_API_BIND`
- `MIND_API_PUBLIC_URL`
- `MIND_API_SECRET_KEY`
- `MIND_DEFAULT_MODEL_PROFILE`

Provider（按需配置）：

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`

可选基础设施（当前阶段非必需，按需启用）：

- `MIND_REDIS_URL`
- `MIND_S3_ENDPOINT`
- `MIND_S3_ACCESS_KEY`
- `MIND_S3_SECRET_KEY`

### 7.4 运维约束

- API 启动时必须显式执行 migration 检查
- worker 启动时必须校验 schema version
- `health` 与 `readiness` 必须区分
- 所有容器都必须有健康检查
- 关键数据卷必须显式挂载

---

## 8. 可执行工作包

本轮实现按 `WP-0 ~ WP-6` 推进；`WP-7 / WP-8` 保留为后续阶段。

### 依赖顺序

```
WP-0 (CLI 拆分)
  └─> WP-1 (应用服务层)
        ├─> WP-2 (用户状态与执行策略)
        │     └─> WP-3 (REST API)
        │           └─> WP-4 (MCP Server)
        ├─> WP-5 (部署与 compose) ← 依赖 WP-3
        └─> WP-6 (产品 CLI) ← 依赖 WP-1 + WP-2
WP-7 (Capability / Provider) ← 依赖 WP-1，可与 WP-3~6 并行
WP-8 (Telemetry 与前端就绪) ← 依赖 WP-1
```

说明：

- `WP-0` 必须最先完成，解除命名空间冲突
- `WP-1` 是所有产品化 transport 和 CLI 的前置依赖
- `WP-2` 在 `WP-3` 之前完成，确保 REST 入口启动时已有完整上下文
- `WP-7 / WP-8` 不属于本轮交付范围，继续作为后续产品化阶段

### `WP-0` CLI 命名空间分离

状态：已实现（`2026-03-10`）

目标：

- 现有开发/验收 CLI 改名为 `mindtest`
- `mind` 命名空间留给产品级 CLI

交付物：

- packaging script entry 更新
- CLI 文档迁移说明
- 兼容策略说明

MUST-PASS：

1. `mindtest -h` 覆盖现有开发 CLI 一级命令族 `= 100%`
2. `mind` 不再指向开发/验收总控台
3. 文档和示例中产品入口与开发入口混用率 `= 0`

### `WP-1` 应用服务层

状态：已实现（`2026-03-10`）

目标：

- 建立统一应用服务与 envelope

交付物：

- `mind/app/*`
- 统一 request / response / error contract

MUST-PASS：

1. 产品级 `remember / recall / ask / governance / jobs / user_state / status` 全部通过应用服务层
2. 统一 error envelope 覆盖率 `= 100%`
3. `request_id / idempotency_key / trace_ref` 字段覆盖率 `= 100%`

### `WP-2` 用户状态与执行策略

状态：已实现（`2026-03-10`）

目标：

- 建立正式的 `PrincipalContext / SessionContext / NamespaceContext / ExecutionPolicy`

交付物：

- 状态 contract
- 状态解析服务
- provenance 投影边界说明

MUST-PASS：

1. 产品入口的调用上下文完整率 `= 100%`
2. `tenant / user / session / conversation / policy` 解析成功率 `= 100%`
3. provenance 与产品上下文字段混用绕过率 `= 0`

### `WP-3` REST API v1

状态：已实现（`2026-03-10`）

目标：

- 暴露正式 HTTP 服务

交付物：

- `FastAPI` app
- OpenAPI schema
- auth（至少 API key）/ pagination / health endpoints

MUST-PASS：

1. 最小资源面全部可达
2. `ProductTransportScenarioSet v1` 的 REST 场景通过率 `>= 0.95`
3. 健康检查、ready 检查、统一错误 contract 全部通过
4. 未认证请求被拒绝率 `= 100%`

### `WP-4` MCP Server v1

状态：已实现（`2026-03-10`）

目标：

- 暴露正式 MCP 接入

交付物：

- MCP server
- tool catalog
- session 映射

MUST-PASS：

1. 最小 tool 面全部可达
2. REST 与 MCP 同语义调用一致性 `>= 0.95`
3. MCP session 到 `SessionContext` 的映射成功率 `= 100%`

### `WP-5` 部署与 compose

状态：已实现（`2026-03-10`）

目标：

- 形成本地联调和初期部署的标准资产

交付物：

- `compose.yaml`
- Dockerfiles
- `.env.example`
- health / readiness / migrate entrypoint

MUST-PASS：

1. `compose up` 后 `api / worker / postgres` 健康率 `= 100%`
2. Alembic migration 自动执行成功率 `= 100%`
3. `DeploymentSmokeSuite v1` 场景通过率 `>= 0.95`

### `WP-6` 产品 CLI `mind`

状态：已实现（`2026-03-10`）

目标：

- 形成真正的产品 CLI

交付物：

- `mind remember`
- `mind recall`
- `mind ask`
- `mind history`
- `mind session`
- `mind status`
- `mind config`

MUST-PASS：

1. `ProductCliExperienceBench v1` 场景通过率 `>= 0.95`
2. `mind` 不暴露 phase/gate/demo 等开发命令
3. 本地模式与远程 API 模式的核心行为一致性 `>= 0.95`

### `WP-7` Capability / Provider Layer

状态：后续阶段

目标：

- 把后续 Phase K 的能力层产品化接入

交付物：

- provider adapter
- provider config
- fallback / trace

MUST-PASS：

1. `summarize / reflect / answer / offline_reconstruct` 统一 capability 接口覆盖 `= 100%`
2. `openai / claude / gemini` 兼容样例通过率 `>= 0.95`
3. provider 不可用时 `fallback_success + structured_failure = 100%`

### `WP-8` Dev Telemetry 与前端就绪

状态：后续阶段

目标：

- 把后续 Phase L / M 的观测与前端前置条件产品化

交付物：

- telemetry event schema
- dev-mode 开关
- frontend-facing query contract

MUST-PASS：

1. 内部执行链可回放样例比例 `>= 0.95`
2. debug 数据字段完备度 `>= 0.95`
3. 前端 contract 与 telemetry contract 漂移率 `= 0`

---

## 9. 统一验收工件

产品化阶段需要新增以下版本化工件：

- `UserStateScenarioSet v1`
- `ProductTransportScenarioSet v1`
- `DeploymentSmokeSuite v1`
- `ProductCliExperienceBench v1`

最小要求：

- `UserStateScenarioSet v1`：至少 `30` 个场景；覆盖 principal / tenant / session / conversation / policy
- `ProductTransportScenarioSet v1`：至少 `40` 个场景；覆盖 REST / MCP / CLI 的核心行为一致性
- `DeploymentSmokeSuite v1`：至少 `20` 个场景；覆盖 compose、迁移、health、worker、provider config
- `ProductCliExperienceBench v1`：至少 `30` 个场景；覆盖 `remember / recall / ask / history / session / status / config`

---

## 10. `WP-0 ~ WP-6` 总验收标准

当以下条件同时满足时，本轮产品化交付才算完成：

1. `mindtest` 与 `mind` 已完成命名空间分离
2. 应用服务层已经成为所有产品入口的唯一业务边界
3. `REST API`、`MCP` 和产品 CLI 都已通过统一场景回归
4. `compose` 联调、迁移、API、worker、Postgres 全部通过部署 smoke
5. 用户状态、会话状态、执行策略与 provenance 边界已正式冻结
6. `pytest tests/` 全量回归通过

---

## 11. 与现有阶段的关系

这份产品化方案不推翻历史 `PASS`：

- `Phase J` 继续代表“统一开发/验收 CLI 基线已经存在”
- 但产品化 addendum 明确要求：
  - 这套 CLI 若保留，必须迁移为 `mindtest`
  - 产品级 `mind` 必须重新按本文件实现

当前仓库状态：

- `mindtest` 已保留为开发/验收 CLI
- `mind` 已切换为产品 CLI
- `mind/app`、`mind/api`、`mind/mcp`、部署资产与产品测试工件已经到位

与后续阶段的关系：

- `WP-7` 对应后续 Phase K 的产品化落地
- `WP-8` 对应后续 Phase L / M 的产品化落地
- 更重的 `Phase N / O` 仍然是治理 reshape 与 persona projection

换句话说：

**这份文档定义的是“把已有研究原型变成产品”的执行蓝图。**
