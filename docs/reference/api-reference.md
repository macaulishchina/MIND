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

## Frontend

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/v1/frontend/catalog` | frontend catalog |
| `GET` | `/v1/frontend/gate-demo` | frontend gate/demo summary |
| `POST` | `/v1/frontend/ingest` | frontend ingest |
| `POST` | `/v1/frontend/retrieve` | frontend retrieve |
| `POST` | `/v1/frontend/access` | frontend access |
| `POST` | `/v1/frontend/offline` | frontend offline submit |
| `GET` | `/v1/frontend/benchmark:workspace` | load benchmark workspace metadata for datasets, slices, raw sources, and reports |
| `POST` | `/v1/frontend/benchmark:run` | run lifecycle benchmark and persist artifacts |
| `POST` | `/v1/frontend/benchmark:report` | load persisted lifecycle benchmark report |
| `POST` | `/v1/frontend/benchmark:slice:generate` | compile a raw public dataset sample into a local benchmark slice |
| `GET` | `/v1/frontend/settings` | frontend settings page |
| `POST` | `/v1/frontend/settings:preview` | preview settings mutation |
| `POST` | `/v1/frontend/settings:apply` | apply settings mutation |
| `POST` | `/v1/frontend/settings:restore` | restore previous settings snapshot |
| `GET` | `/v1/frontend/debug:workspace` | load debug filter metadata for searchable troubleshooting queries |
| `POST` | `/v1/frontend/debug:timeline` | frontend debug timeline query |

## OpenAPI

启动 `mind-api` 后，OpenAPI UI 默认可在 `/docs` 查看。
