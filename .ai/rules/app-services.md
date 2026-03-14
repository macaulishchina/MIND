# Rules: Application Services (`mind/app/services/`)

> Load this file when modifying anything under `mind/app/services/`.

---

## Scope

App services are the bridge between transports (REST/MCP/CLI) and domain logic.
They handle the request envelope, context resolution, and error mapping.

## Key Files

| File | Purpose |
|------|---------|
| `mind/app/contracts.py` | `AppRequest`, `AppResponse`, `AppError`, `AppErrorCode` |
| `mind/app/context.py` | Execution contexts (`PrincipalContext`, `SessionContext`, etc.) |
| `mind/app/errors.py` | Error hierarchy + `map_domain_error()` |
| `mind/app/registry.py` | `AppServiceRegistry` + `build_app_registry()` |
| `mind/app/_service_utils.py` | Shared helpers (`new_response`, `result_status`, `latest_trace_ref`) |
| `mind/app/runtime.py` | `GlobalRuntimeManager` |
| `mind/app/services/*.py` | Individual service implementations |

## Standard Method Pattern

Every app service method MUST follow this pattern:

```python
def method_name(self, req: AppRequest) -> AppResponse:
    # 1. Apply request defaults (if resolver is present)
    if self._request_defaults_resolver is not None:
        req = self._request_defaults_resolver(req, ...)
    
    # 2. Create response envelope
    resp = new_response(req)
    
    # 3. Resolve execution context
    ctx = resolve_execution_context(req.principal, req.session, req.policy, req.provider_selection)
    
    # 4. Extract inputs from req.input dict
    data = req.input.get("key", default)
    
    # 5. Call domain/primitive service (in try/except)
    try:
        result = self._primitive.operation(data, ctx)
    except Exception as exc:
        resp.status = AppStatus.ERROR
        resp.error = map_domain_error(exc)
        return resp
    
    # 6. Map result to response
    resp.status = result_status(result)
    resp.result = {... extract from result ...}
    return resp
```

## Rules

1. **Envelope pattern**: Always `AppRequest` in, `AppResponse` out. No exceptions.

2. **Register in registry**: New services MUST be added as a field in
   `AppServiceRegistry` and wired in `build_app_registry()`.

3. **Error mapping**: ALWAYS catch domain exceptions and map via
   `map_domain_error()`. Never let raw exceptions propagate to transport.

4. **No direct store access**: App services call domain services or primitives.
   They do NOT call `store.insert_object()` directly. Exception:
   `MemoryQueryService` may read from store for listing/search operations.

5. **Request defaults**: If the service has a `_request_defaults_resolver`,
   ALWAYS call it at the start of the method.

6. **Scheduler integration**: If a service auto-schedules offline jobs,
   inject `OfflineJobScheduler` and call it after successful operations.

## Common Mistakes

- Forgetting to add the service to `AppServiceRegistry`.
- Forgetting to wire it in `build_app_registry()`.
- Letting domain exceptions escape to the transport layer.
- Accessing the store directly instead of going through primitives.
