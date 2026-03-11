# Error Reference

## Top-level status

| Status | 含义 |
|---|---|
| `ok` | 成功 |
| `error` | 处理失败 |
| `rejected` | 业务拒绝 |
| `not_found` | 目标不存在 |
| `unauthorized` | 未授权 |

## Error payload

`AppError` 包含：

- `code`
- `message`
- `retryable`
- `details`

## 常见错误码

### Validation

- `validation_error`
- `conflict`
- `authorization_error`
- `not_found`

### Store

- `store_error`

### Access / Governance / Offline

- `access_service_error`
- `governance_invalid_stage`
- `governance_missing_audit`
- `governance_execution_failed`
- `offline_maintenance_error`

### Primitive-origin

常见包括：

- `capability_required`
- `budget_exhausted`
- `object_not_found`
- `unsupported_query_mode`
- `schema_invalid`
- `unsafe_content`

完整枚举以 [mind/app/contracts.py](/home/macaulish/workspace/MIND/mind/app/contracts.py) 中的 `AppErrorCode` 为准。
