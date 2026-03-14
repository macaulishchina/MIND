# Checklist: Adding a New Application Service

Use this checklist when creating a brand new service under `mind/app/services/`.

---

## Pre-work

- [ ] Read `.ai/rules/app-services.md`
- [ ] If this change spans more than 5 files or multiple subsystems, create or update `PLANS.md` from `.ai/templates/PLANS.md`
- [ ] Determine which domain service or primitive this wraps
- [ ] Confirm the service doesn't already exist (check `mind/app/services/`)

## Implementation

- [ ] Create `mind/app/services/<name>.py` with service class
- [ ] Follow the standard method pattern (AppRequest → AppResponse)
- [ ] Use `map_domain_error()` for all exception handling
- [ ] Use `new_response()` and `result_status()` from `_service_utils`

## Registry Integration

- [ ] Add service field to `AppServiceRegistry` dataclass in `mind/app/registry.py`
- [ ] Wire service instantiation in `build_app_registry()` function
- [ ] Add any necessary imports

## Testing

- [ ] Create `tests/test_<service_name>.py`
- [ ] Test happy path (successful operation)
- [ ] Test error path (domain exception → AppError mapping)
- [ ] Test edge cases (empty input, missing fields)

## Transport (if exposed)

- [ ] Add REST endpoint(s) → see `new-endpoint.md` checklist
- [ ] Add MCP tool(s) if applicable
- [ ] Add CLI command(s) if applicable

## Documentation

- [ ] Add docstring to service class and all public methods
- [ ] Update transport docs if endpoints were added

## Verification

- [ ] `uv run ruff check mind/ tests/` — zero errors
- [ ] `uv run mypy mind/ tests/` — zero errors
- [ ] `uv run pytest tests/test_<service_name>.py -v` — all pass
- [ ] `uv run pytest tests/ -x` — full suite passes
