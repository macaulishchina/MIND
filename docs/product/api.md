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
- `GET /v1/frontend/settings`
- `POST /v1/frontend/settings:preview`
- `POST /v1/frontend/settings:apply`
- `POST /v1/frontend/settings:restore`
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
