# Rules: App Core (`mind/app/` except `mind/app/services/`)

> Load this file when modifying application-layer core modules.

---

## Scope

These modules define app-layer contracts, context resolution, error mapping,
registry wiring, runtime helpers, and shared frontend-facing app adapters.

## Rules

1. **Keep contracts stable**: `AppRequest`, `AppResponse`, `AppError`, and
   shared context models are public app-layer contracts. Changes here require
   transport, tests, and docs review.

2. **Single composition root**: `build_app_registry()` remains the only place
   where production services are wired together. Do not instantiate new app or
   domain services ad hoc in transport modules.

3. **No domain logic drift**: `mind/app/` may resolve context, map errors, and
   shape responses, but business rules stay in domain services and primitives.

4. **Keep shared helpers generic**: `_service_utils.py`, `runtime.py`,
   `runtime_env.py`, and app-level frontend helpers should stay reusable across
   transports instead of growing transport-specific branches.

5. **Sync context changes end-to-end**: If you add or rename a request context
   field, update resolver code, registry wiring, transport builders, and tests
   in the same change.

## Common Mistakes

- Putting domain logic into registry or contract modules.
- Updating app contracts without adjusting transport projections.
- Creating second composition roots in CLI or API code.
