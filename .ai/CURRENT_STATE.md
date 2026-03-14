# MIND Current State

> Last updated: 2026-03-13

---

## 1. Version & Phase

- **Version**: 0.2.0
- **Current phase**: Phase N (Productization wrap-up + Growth features)
- **Completed phases**: B, C, D, E, F, G, H, I, J, K, L, M
- **WP status**: WP-0 through WP-6 implemented, WP-7+ in progress

---

## 2. Frozen Interfaces (DO NOT break)

### REST API v1
All endpoints under `/v1/` are stable. Do not rename, remove, or change
required parameters of existing endpoints.

### MCP Tools
Published tool names and parameter schemas are stable. Version bump required
for breaking changes.

### Product CLI (`mind`)
Command signatures are stable. Adding new subcommands is fine; changing
existing ones requires migration guidance.

### Dev CLI (`mindtest`)
May change freely — used for development and testing only.

---

## 3. Active Work

| Item | Status | Description |
|------|--------|-------------|
| Growth features G1-G15 | Just committed | Feedback endpoint, priority, health, dense retrieval |
| Phase N productization | In progress | Final productization gates |
| AI-driven development | Starting | `.ai/` governance infrastructure |

---

## 4. Known Technical Debt

- Dense retrieval (`sentence-transformers`) is optional — not all deployments have it.
- Some `Any` types in `AppRequest.input` dict — consider typed alternatives per-service.
- Offline worker uses polling (10s interval) — consider event-driven approach later.

---

## 5. Environment Quick Reference

```bash
# Dev environment
./scripts/dev.sh                    # Full stack with hot reload
uv run pytest tests/ -x             # Run tests
uv run ruff check mind/ tests/      # Lint
uv run mypy mind/ tests/ scripts/   # Type check

# Ports
# API:        18600
# Docs (dev): 18602
# PostgreSQL: 18605
# Debugpy:    18606
```
