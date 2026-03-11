# 应用服务层

`mind/app` 是产品化之后最关键的一层。

## 责任

- 定义统一 `AppRequest` / `AppResponse`
- 吸收 transport 差异
- 把 domain error 统一映射成 `AppError`
- 形成 `request_id / idempotency_key / trace_ref / audit_ref`

## 服务面

- `MemoryIngestService`
- `MemoryQueryService`
- `MemoryAccessService`
- `GovernanceAppService`
- `OfflineJobAppService`
- `UserStateService`
- `SystemStatusService`

## Registry

`build_app_registry()` 负责：

- 构建 store
- 组装 domain services
- 组装 app services
- 向 transport 暴露统一依赖面

这使得：

- CLI local 模式可直接复用
- REST lifespan 可复用
- MCP server 可复用

## 文档含义

产品文档默认优先描述 app-layer 语义，而不是更底层的 primitive 内部细节；后者继续保留在 foundation/design 文档中。
