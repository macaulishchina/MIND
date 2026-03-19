# REST API 指南

REST 服务由 `mind-api` 暴露，底层统一调用 `mind/app`。

## 启动

```bash
export MIND_POSTGRES_DSN='postgresql+psycopg://postgres:postgres@127.0.0.1:18605/mind'
export MIND_API_KEY='change-me'
uv run mind-api
```

`mind-api` 没有 SQLite fallback；启动前必须准备 PostgreSQL DSN。使用 compose 或 `./scripts/dev.sh` 时，这个环境变量会由运行时文件提供。

## 认证

所有正式端点都要求：

```text
X-API-Key: <your key>
```

当前实现不支持 JWT/OAuth；如果 `MIND_API_KEY` 没有配置，认证依赖会直接拒绝请求。

## 文档与调试

- OpenAPI UI：`/docs`
- Liveness / Readiness / Config 等系统端点见下方 [System](#system) 小节

## 资源面

### Memories

- `POST /v1/memories`
- `GET /v1/memories/{memory_id}`
- `GET /v1/memories`
- `POST /v1/memories:search`
- `POST /v1/memories:recall`

### Access

- `POST /v1/access:ask`
- `POST /v1/access:run`
- `POST /v1/access:explain`

### Governance

- `POST /v1/governance:plan-conceal`
- `POST /v1/governance:preview`
- `POST /v1/governance:execute-conceal`

### Jobs

- `POST /v1/jobs`
- `GET /v1/jobs/{job_id}`
- `GET /v1/jobs`
- `DELETE /v1/jobs/{job_id}`

### Frontend

- `GET /v1/frontend/catalog`
- `GET /v1/frontend/gate-demo`
- `POST /v1/frontend/ingest`
- `POST /v1/frontend/retrieve`
- `POST /v1/frontend/access`
- `POST /v1/frontend/offline`
- `GET /v1/frontend/benchmark:workspace`
- `POST /v1/frontend/benchmark:run`
- `POST /v1/frontend/benchmark:report`
- `POST /v1/frontend/benchmark:slice:generate`
- `GET /v1/frontend/settings`
- `POST /v1/frontend/settings:preview`
- `POST /v1/frontend/settings:apply`
- `POST /v1/frontend/settings:restore`
- `GET /v1/frontend/debug:workspace`
- `POST /v1/frontend/debug:timeline`

### User State

- `POST /v1/sessions`
- `GET /v1/sessions`
- `GET /v1/sessions/{session_id}`
- `GET /v1/users/{principal_id}`
- `PATCH /v1/users/{principal_id}/preferences`
- `GET /v1/users/{principal_id}/defaults`

### System

- `GET /v1/system/health`
- `GET /v1/system/readiness`
- `GET /v1/system/config`
- `GET /v1/system/provider-status`
- `POST /v1/system/provider-status:resolve`

## 请求与响应

HTTP router 会先构建 `AppRequest`，再调用对应 app service，返回统一 `AppResponse`：

- `status`
- `result`
- `error`
- `trace_ref`
- `audit_ref`
- `request_id`
- `idempotency_key`

另外，中间件会透传或生成 `X-Request-ID`。

所有通过 `AppRequest` 进入的 REST 调用都可以在 envelope 中附带
`provider_selection`。如果只是想做一次请求级解析预览，直接调用
`POST /v1/system/provider-status:resolve`；如果请求后续进入 capability-backed
执行链路，这个选择也会继续向下传递，并作为本次请求的 provider override 生效。

当前已经显式接入的 capability-backed 路径包括：

- primitive `summarize`
- primitive `reflect`
- access `answer`
- offline `offline_reconstruct`

对于 `POST /v1/jobs` 这类 deferred execution 入口，如果请求里带了
`provider_selection`，app service 会把它固化到 offline job，后续 worker 执行时再把
这个选择回放给 capability layer。也就是说，job submission 和 job execution 使用的
provider 语义现在是一致的。

`POST /v1/access:ask` / `POST /v1/access:run` / `POST /v1/access:explain`
现在除了返回检索/上下文信息，也会在 result 中包含本次 capability answer 的输出：

- `answer_text`
- `answer_support_ids`
- `answer_trace`

如果请求带了 `provider_selection`，这个 provider override 会作用到这次 answer 生成。

`POST /v1/frontend/access` 会把 access 结果继续投影成稳定的 frontend-facing contract。
除了保留 `summary`、candidate/selected evidence 和 `trace_ref`，现在还会在 result 中显式返回：

- `answer.text`
- `answer.support_ids`
- `answer.trace.provider_family`
- `answer.trace.fallback_used`
- `answer.trace.fallback_reason`

这让 frontend shell 和其他 frontend client 不需要直接依赖 raw telemetry payload，也不需要从
`summary` 反推回答语义。

`POST /v1/frontend/benchmark:run` 会同步执行 memory lifecycle benchmark：真实走
`write_raw`、`summarize`、`reflect`、`reorganize_simple`、`promote_schema` 和分阶段 `ask`，
然后把 report、telemetry、SQLite store 持久化到 benchmark artifact 目录，并返回稳定的
frontend-facing benchmark report 投影。请求体目前包含：

- `dataset_name`
- `source_path`

`POST /v1/frontend/benchmark:report` 会读取已持久化的 benchmark report。请求体可选：

- `run_id`：指定某次 benchmark 运行；省略时读取最近一次持久化报告。

`GET /v1/frontend/benchmark:workspace` 会返回生命周期基准工作台需要的全部下拉元数据：

- `datasets[]`：可选 public dataset、摘要、raw source 类型、默认输出路径
- `raw_sources[]`：当前仓库中可直接用于编译 slice 的 raw 数据样例
- `slice_options[]`：可直接运行 benchmark 的 local slice 列表
- `report_options[]`：已持久化的历史 benchmark 报告，按最近时间排序
- `default_*`：页面初始化时建议选中的数据集、slice、raw source、输出路径和最近报告

`POST /v1/frontend/benchmark:slice:generate` 会把 raw public dataset 样例编译成可直接运行的
local slice，并返回生成结果。请求体包含：

- `dataset_name`
- `raw_source_path`
- `output_path`
- `selector_values`：可选；SciFact 表示 claim ids，LoCoMo / HotpotQA 表示 example ids
- `max_items`：可选；未给 selector 时用于截取 raw 数据

返回结果会包含：

- `source_path`：生成后的 local slice 路径
- `bundle_count`
- `sequence_count`
- `selector_kind`
- `selector_values`
- `max_items`

benchmark report 结果会返回：

- `run_id`
- `report_path`
- `telemetry_path`
- `store_path`
- `stage_reports[]`：每个阶段的 ask / memory / cost 指标
- `frontend_debug_query.run_id`：可直接继续喂给 `POST /v1/frontend/debug:timeline`

`GET /v1/frontend/debug:workspace` 会返回问题排查页面需要的筛选元数据：

- `default_run_id`：页面默认建议查看的最近一次请求
- `run_options[]` / `operation_options[]` / `object_options[]`
- `job_options[]` / `workspace_options[]`
- `scope_options[]` / `event_kind_options[]`
- `earliest_occurred_at` / `latest_occurred_at`：当前 telemetry 可筛选的时间范围

`POST /v1/frontend/debug:timeline` 继续负责真正查询处理记录。除了现有的
`run_id` / `operation_id` / `job_id` / `workspace_id` / `object_id` 之外，
现在还支持：

- `occurred_after`
- `occurred_before`
- `scopes[]`
- `event_kinds[]`
- `limit`

这些条件全部都是可选的；某一项不传就不会参与过滤。

`provider_selection` 的结构如下：

```json
{
  "provider_selection": {
    "provider": "openai",
    "model": "gpt-4.1-mini",
    "endpoint": "https://api.openai.com/v1/responses",
    "timeout_ms": 12000,
    "retry_policy": "none"
  }
}
```

## 示例

```bash
curl \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: change-me' \
  http://127.0.0.1:18600/v1/memories \
  -d '{"content":"hello","episode_id":"ep-1","timestamp_order":1}'
```
