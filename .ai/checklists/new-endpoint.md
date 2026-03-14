# Checklist: Adding a New Endpoint

Use this checklist when adding a REST API, MCP tool, or CLI command.

---

## Pre-work

- [ ] If this change spans more than 5 files or multiple subsystems, create or update `PLANS.md` from `.ai/templates/PLANS.md`

## REST API Endpoint

- [ ] Read `.ai/rules/api.md`
- [ ] Add route handler in `mind/api/<router>.py`
- [ ] Route handler is thin: build AppRequest → call service → return response
- [ ] Register router in `mind/api/app.py` (if new router file)
- [ ] Add Pydantic request/response models for OpenAPI docs
- [ ] Correct HTTP status code mapping
- [ ] Authentication applied (unless public endpoint)
- [ ] Add tests in `tests/test_<endpoint>.py`
- [ ] Update `docs/product/api.md`
- [ ] Update `docs/reference/api-reference.md`

## MCP Tool

- [ ] Add tool handler in `mind/mcp/server.py`
- [ ] Follow existing tool pattern (parameter schema, description)
- [ ] Add tests in `tests/test_mcp_<tool>.py`
- [ ] Update `docs/product/mcp.md`
- [ ] Update `docs/reference/mcp-tool-reference.md`

## CLI Command

- [ ] Add command to `mind/product_cli.py` (product) or `mind/cli.py` (dev)
- [ ] Add entry point in `pyproject.toml` → `[project.scripts]` (if new top-level)
- [ ] Add tests in `tests/test_cli_<command>.py`
- [ ] Update `docs/product/cli.md`
- [ ] Update `docs/reference/cli-reference.md`

## Verification

- [ ] `uv run ruff check mind/ tests/` — zero errors
- [ ] `uv run mypy mind/ tests/` — zero errors
- [ ] `uv run python scripts/ai_health_check.py --report-for-ai` — quick local health check passes
- [ ] `uv run python scripts/ai_health_check.py --full --report-for-ai` — full health check passes
- [ ] Endpoint is backward-compatible (no breaking changes to existing endpoints)
