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

## 8. Documentation Sync Rules

From `docs/docs-authoring.md`:

| Code change | Docs to update |
|-------------|----------------|
| CLI commands | `docs/product/cli.md` + `docs/reference/cli-reference.md` |
| REST routes | `docs/product/api.md` + `docs/reference/api-reference.md` |
| MCP tools | `docs/product/mcp.md` + `docs/reference/mcp-tool-reference.md` |
| Config/env vars | `docs/product/deployment.md` + `docs/reference/config-reference.md` |
| Architecture changes | `docs/architecture/` (relevant file) |

---

## 9. Verification Checklist (After Any Change)

- [ ] `uv run ruff check mind/ tests/ scripts/` — zero errors
- [ ] `uv run mypy mind/ tests/ scripts/` — zero errors
- [ ] `uv run pytest tests/ -x` — all pass
- [ ] Changed code has corresponding test(s)
- [ ] Documentation updated per sync rules above
- [ ] No new `# type: ignore` without justification
