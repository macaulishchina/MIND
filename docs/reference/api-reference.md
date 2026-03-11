# API Reference

## 认证

所有正式端点都要求：

```text
X-API-Key: <key>
```

## 响应 envelope

所有 router 都返回统一 `AppResponse`：

| 字段 | 说明 |
|---|---|
| `status` | `ok` / `error` / `rejected` / `not_found` / `unauthorized` |
| `result` | 业务结果 |
| `error` | 结构化错误 |
| `trace_ref` | 执行链引用 |
| `audit_ref` | 审计引用 |
| `request_id` | 请求标识 |
| `idempotency_key` | 幂等键 |

## Memories

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/v1/memories` | remember |
| `GET` | `/v1/memories/{memory_id}` | get memory |
| `GET` | `/v1/memories` | list memories |
| `POST` | `/v1/memories:search` | search memories |
| `POST` | `/v1/memories:recall` | recall memories |

`GET /v1/memories` 支持：

- `limit`（1–100，默认 50）
- `offset`（>= 0，默认 0）
- `episode_id`
- `task_id`
- `object_types`
- `statuses`

## Access

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/v1/access:ask` | ask |
| `POST` | `/v1/access:run` | run_access |
| `POST` | `/v1/access:explain` | explain_access |

## Governance

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/v1/governance:plan-conceal` | plan |
| `POST` | `/v1/governance:preview` | preview |
| `POST` | `/v1/governance:execute-conceal` | execute |

## Jobs

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/v1/jobs` | submit job |
| `GET` | `/v1/jobs/{job_id}` | get job |
| `GET` | `/v1/jobs` | list jobs |
| `DELETE` | `/v1/jobs/{job_id}` | cancel job |

`GET /v1/jobs` 支持：

- `status`
- `limit`（1–100，默认 50）
- `offset`（>= 0，默认 0）

## Sessions and Users

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/v1/sessions` | open session |
| `GET` | `/v1/sessions` | list sessions |
| `GET` | `/v1/sessions/{session_id}` | get session |
| `GET` | `/v1/users/{principal_id}` | get principal |
| `PATCH` | `/v1/users/{principal_id}/preferences` | update preferences |
| `GET` | `/v1/users/{principal_id}/defaults` | get runtime defaults |

## System

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/v1/system/health` | liveness |
| `GET` | `/v1/system/readiness` | readiness |
| `GET` | `/v1/system/config` | config summary |

## OpenAPI

启动 `mind-api` 后，OpenAPI UI 默认可在 `/docs` 查看。
