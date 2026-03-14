# Rules: REST API Layer (`mind/api/`)

> Load this file when modifying anything under `mind/api/`.

---

## Scope

FastAPI REST endpoints. Thin transport layer that delegates to app services.

## Key Files

| File | Purpose |
|------|---------|
| `app.py` | FastAPI app factory, lifespan, exception handlers, router registration |
| `auth.py` | API key authentication (`X-API-Key` header) |
| `pagination.py` | Pagination helpers |
| `memories.py` | Memory CRUD endpoints |
| `access.py` | Access mode endpoints |
| `governance.py` | Governance endpoints |
| `jobs.py` | Offline job endpoints |
| `sessions.py` | Session endpoints |
| `users.py` | User/principal endpoints |
| `system.py` | Health/status endpoints |
| `frontend.py` | Frontend experience endpoints |

## Rules

1. **Thin layer**: Route handlers MUST only:
   - Build an `AppRequest` from the HTTP request
   - Call the appropriate app service method
   - Convert the `AppResponse` to an HTTP response

2. **No business logic**: Never put domain logic in route handlers.

3. **Router registration**: New router files MUST be registered in `app.py`
   via `app.include_router(router, prefix="/v1/...")`.

4. **Versioned prefix**: All endpoints under `/v1/`. No unversioned routes
   (except `/health`).

5. **Authentication**: Protected endpoints use the `X-API-Key` dependency.
   Public endpoints (`/health`) are exempt.

6. **Status code mapping**:
   - `AppStatus.OK` → 200
   - `AppStatus.ERROR` → 500 (or specific error code)
   - `AppStatus.NOT_FOUND` → 404
   - `AppStatus.REJECTED` → 422
   - `AppStatus.UNAUTHORIZED` → 401/403

7. **Backward compatibility**: Existing endpoint paths, methods, and required
   parameters MUST NOT change. Adding optional parameters is OK.

8. **Docs sync**: Update `docs/product/api.md` and `docs/reference/api-reference.md`.

## Common Mistakes

- Putting business logic in the route handler.
- Forgetting to register the router in `app.py`.
- Breaking existing endpoint contracts.
