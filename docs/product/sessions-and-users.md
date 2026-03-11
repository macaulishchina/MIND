# 用户与会话

产品化后，MIND 不再只围绕 object/store 运行，还会显式维护用户态上下文。

## 核心上下文

- `PrincipalContext`
- `NamespaceContext`
- `SessionContext`
- `ExecutionPolicy`

## 当前持久化对象

### principals

保存：

- `principal_id`
- `principal_kind`
- `tenant_id`
- `user_id`
- `roles`
- `capabilities`
- `preferences`

### sessions

保存：

- `session_id`
- `principal_id`
- `conversation_id`
- `channel`
- `client_id`
- `device_id`
- `started_at`
- `last_active_at`
- `metadata`

### namespaces

保存：

- `namespace_id`
- `tenant_id`
- `project_id`
- `workspace_id`
- `visibility_policy`

## 当前产品面

通过 CLI：

- `mind session open`
- `mind session list`
- `mind session show`

通过 REST：

- `POST /v1/sessions`
- `GET /v1/sessions`
- `GET /v1/sessions/{session_id}`
- `GET /v1/users/{principal_id}`
- `PATCH /v1/users/{principal_id}/preferences`
- `GET /v1/users/{principal_id}/defaults`

## Defaults 解析

`UserStateService` 会优先从持久化用户偏好推导 runtime defaults，当前包括：

- `default_access_mode`
- `budget_limit`
- `retention_class`
- `dev_mode`
- `conceal_visibility`
- `fallback_policy`

## Provenance 边界

产品上下文和 provenance 已经分离：

- 产品调用先形成 principal/session/namespace/policy
- provenance 再从这些上下文投影
- provenance 不能反过来替代产品上下文
