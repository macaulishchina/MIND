# REST API 指南

REST 服务由 `mind-api` 暴露，底层统一调用 `mind/app`。

## 启动

```bash
export MIND_API_KEY='change-me'
uv run mind-api
```

## 认证

所有正式端点都要求：

```text
X-API-Key: <your key>
```

当前实现不支持 JWT/OAuth；如果 `MIND_API_KEY` 没有配置，认证依赖会直接拒绝请求。

## 文档与调试

- OpenAPI UI：`/docs`
- Liveness：`/v1/system/health`
- Readiness：`/v1/system/readiness`
- Config summary：`/v1/system/config`

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

### User State

- `POST /v1/sessions`
- `GET /v1/sessions`
- `GET /v1/sessions/{session_id}`
- `GET /v1/users/{principal_id}`
- `PATCH /v1/users/{principal_id}/preferences`
- `GET /v1/users/{principal_id}/defaults`

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

## 示例

```bash
curl \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: change-me' \
  http://127.0.0.1:8000/v1/memories \
  -d '{"content":"hello","episode_id":"ep-1","timestamp_order":1}'
```
