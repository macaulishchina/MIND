# MIND Change Protocol

> When you change A, you MUST also change B. This is the synchronization map.

---

## 1. Adding a New Primitive

| Step | File(s) to change |
|------|--------------------|
| 1. Add enum member | `mind/primitives/contracts.py` → `PrimitiveName` |
| 2. Add request/response models | `mind/primitives/contracts.py` |
| 3. Implement logic | `mind/primitives/service.py` → new method |
| 4. Add tests | `tests/test_<primitive_name>.py` |
| 5. Update docs | `docs/reference/api-reference.md` (if exposed via API) |

---

## 2. Adding a New App Service

| Step | File(s) to change |
|------|--------------------|
| 1. Create service class | `mind/app/services/<name>.py` |
| 2. Register in registry | `mind/app/registry.py` → `AppServiceRegistry` dataclass + `build_app_registry()` |
| 3. Add tests | `tests/test_<name>.py` |

---

## 3. Adding a New REST Endpoint

| Step | File(s) to change |
|------|--------------------|
| 1. Add route | `mind/api/<router>.py` |
| 2. Register router (if new file) | `mind/api/app.py` → `include_router()` |
| 3. Add Pydantic request/response models | Same router file or `mind/api/models.py` |
| 4. Add tests | `tests/test_<endpoint>.py` |
| 5. Update API docs | `docs/product/api.md` + `docs/reference/api-reference.md` |

---

## 4. Adding a New MCP Tool

| Step | File(s) to change |
|------|--------------------|
| 1. Add tool handler | `mind/mcp/server.py` |
| 2. Add tests | `tests/test_mcp_<tool>.py` |
| 3. Update MCP docs | `docs/product/mcp.md` + `docs/reference/mcp-tool-reference.md` |

---

## 5. Adding a New CLI Command

| Step | File(s) to change |
|------|--------------------|
| 1. Add command | `mind/product_cli.py` (product) or `mind/cli.py` (dev) |
| 2. Register entry point (if new top-level) | `pyproject.toml` → `[project.scripts]` |
| 3. Add tests | `tests/test_cli_<command>.py` |
| 4. Update CLI docs | `docs/product/cli.md` + `docs/reference/cli-reference.md` |

---

## 6. Adding a New Store Method

| Step | File(s) to change |
|------|--------------------|
| 1. Add to protocol | `mind/kernel/store.py` → `MemoryStore` protocol |
| 2. Implement in SQLite | `mind/kernel/store.py` → `SQLiteMemoryStore` |
| 3. Implement in PostgreSQL | `mind/kernel/postgres_store.py` → `PostgresMemoryStore` |
| 4. Add migration (if schema change) | `alembic/versions/` → new migration file |
| 5. Add tests | `tests/test_<store_feature>.py` |

---

## 7. Changing Configuration

| Step | File(s) to change |
|------|--------------------|
| 1. Update config model | `mind/cli_config.py` |
| 2. Update env example | `.env.example` |
| 3. Update docs | `docs/product/deployment.md` + `docs/reference/config-reference.md` |

---

## 8. Adding a New Offline Job

| Step | File(s) to change |
|------|--------------------|
| 1. Add job kind + payload contract | `mind/offline_jobs.py` |
| 2. Add scheduling entrypoint (if enqueue is user-visible or periodic) | `mind/offline/scheduler.py` |
| 3. Implement worker dispatch + execution logic | `mind/offline/service.py` |
| 4. Update app/transport entrypoint if exposed | `mind/app/services/*` + relevant transport module |
| 5. Add tests | `tests/test_offline_*.py` or the closest feature/phase test |
| 6. Update docs | Relevant product/reference docs if externally exposed |

---

## 9. Adding a New Memory Object Type

| Step | File(s) to change |
|------|--------------------|
| 1. Add schema/validation | `mind/kernel/schema.py` |
| 2. Add store protocol + backend support | `mind/kernel/store.py` + `mind/kernel/postgres_store.py` |
| 3. Update primitive/domain handling | Relevant `mind/primitives/*` or domain-service module |
| 4. Add fixtures + tests | `mind/fixtures/` + `tests/` |
| 5. Update docs | `docs/architecture/storage-model.md` + relevant product/reference docs |

---

## 10. Adding or Changing a Provider Adapter

| Step | File(s) to change |
|------|--------------------|
| 1. Add adapter module + protocol wiring | `mind/capabilities/*.py` + `mind/capabilities/service.py` |
| 2. Update config and selection surface | `mind/cli_config.py` + any provider-selection contracts |
| 3. Update status/reporting surfaces if user-visible | Relevant app service, API, CLI, or frontend module |
| 4. Add deterministic tests | Adapter tests + relevant phase-K tests |
| 5. Update docs | `docs/architecture/capability-layer.md` + relevant product/reference docs |

---

## 11. Adding or Changing a Telemetry Event

| Step | File(s) to change |
|------|--------------------|
| 1. Update event contracts | `mind/telemetry/contracts.py` |
| 2. Record/update event at call sites | Relevant feature module + `mind/telemetry/runtime.py` if needed |
| 3. Update audits and gates | `mind/telemetry/audit.py` + `mind/telemetry/audit_rules.py` + `mind/telemetry/gate.py` |
| 4. Add tests | Relevant feature tests + phase-L telemetry tests |
| 5. Update docs | Relevant architecture/product docs if the event is user-visible or operationally important |

---

## 12. Planning a Large Change

| Step | File(s) to change |
|------|--------------------|
| 1. Create or update a repo-root plan | `PLANS.md` from `.ai/templates/PLANS.md` |
| 2. Record scope and constraints | Goal, constraints, non-goals, affected areas |
| 3. Break work into verifiable slices | `## Steps` + `## Verification` |
| 4. Keep plan current during execution | `## Progress Log`, `## Decisions`, `## Open Questions` |
| 5. Close or archive the plan after the work lands | Update final status and follow-ups |

---

## 13. Documentation Sync Rules

From `docs/docs-authoring.md`:

| Code change | Docs to update |
|-------------|----------------|
| CLI commands | `docs/product/cli.md` + `docs/reference/cli-reference.md` |
| REST routes | `docs/product/api.md` + `docs/reference/api-reference.md` |
| MCP tools | `docs/product/mcp.md` + `docs/reference/mcp-tool-reference.md` |
| Config/env vars | `docs/product/deployment.md` + `docs/reference/config-reference.md` |
| Architecture changes | `docs/architecture/` (relevant file) |

---

## 14. Verification Checklist (After Any Change)

- [ ] `uv run ruff check mind/ tests/ scripts/` — zero errors
- [ ] `uv run mypy mind/ tests/ scripts/` — zero errors
- [ ] Run the appropriate health check once for this milestone: `uv run python scripts/ai_health_check.py --report-for-ai` for quick local iteration, or `uv run python scripts/ai_health_check.py --full --report-for-ai` for pre-commit/final verification (`--full` subsumes quick)
- [ ] Changed code has corresponding test(s)
- [ ] Documentation updated per sync rules above
- [ ] No new `# type: ignore` without justification
- [ ] If the change introduced a new sync dependency, update `.ai/CHANGE_PROTOCOL.md`
