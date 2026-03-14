# MIND Project — AI Constitution

> Version: 1.0.0 | Last updated: 2026-03-13
>
> This file is the **single source of truth** for all AI coding agents
> working on the MIND project. It MUST be read before any code change.

---

## 0. How to Use This File

You are an AI coding agent. This file is your operating manual. Follow these rules:

1. **Always read this file first** before making any code change.
2. **Use the routing table** (§6) to load additional rules for the module you are modifying.
3. **Use the checklist** (§7) matching your change type before starting work.
4. **Never violate a MUST rule** — they are non-negotiable.
5. If a rule conflicts with a user's explicit instruction, follow the user — but warn them about the conflict.

---

## 1. Project Identity

MIND is a **productized external memory system for LLM agents**. v0.2.0.
Core philosophy: "Training ends, but memory continues to grow."

- **Language**: Python 3.12+
- **Framework**: FastAPI (REST), MCP SDK (MCP), Click (CLI)
- **Storage**: PostgreSQL 16 + pgvector (prod), SQLite (dev/test)
- **Validation**: Pydantic 2.12+ (strict mode, `extra="forbid"`, `frozen=True`)
- **ORM**: SQLAlchemy 2.0+ (Alembic migrations)

---

## 2. Architecture Invariants (MUST NOT violate)

### 2.1 Layered Architecture

```
Transport (REST / MCP / CLI / Frontend)
    ↓ calls
Application Services  (mind/app/services/)
    ↓ calls
Domain Services  (mind/access/, mind/governance/, mind/capabilities/, mind/offline/)
    ↓ calls
Primitives  (mind/primitives/)
    ↓ calls
Kernel  (mind/kernel/)
```

- **MUST**: Upper layers call down only. Never import from a higher layer.
- **MUST**: All transport endpoints go through `mind/app/services/`. No direct primitive or kernel calls from transport.
- **MUST**: All persistence goes through `MemoryStore` protocol (`mind/kernel/store.py`). No raw SQL outside kernel.

### 2.2 Request/Response Envelope

All application services use `AppRequest` → `AppResponse` envelope pattern:
- Inbound: `AppRequest` (from `mind/app/contracts.py`)
- Outbound: `AppResponse` (from `mind/app/contracts.py`)
- Errors: `AppError` with `AppErrorCode` enum
- **MUST**: Every new app service method takes `AppRequest` and returns `AppResponse`.
- **MUST**: Domain exceptions are mapped to `AppErrorCode` via `map_domain_error()` in `mind/app/errors.py`.

### 2.3 Dependency Injection

`AppServiceRegistry` in `mind/app/registry.py` is the **single composition root**.
- **MUST**: All service wiring happens in `build_app_registry()`.
- **MUST NOT**: Instantiate services outside the registry (except in tests).
- **MUST**: New services are added to `AppServiceRegistry` dataclass fields AND wired in `build_app_registry()`.

### 2.4 Store Protocol

`MemoryStore` is a `Protocol` class. Two implementations: `SQLiteMemoryStore`, `PostgresMemoryStore`.
- **MUST**: New store operations are added to the `MemoryStore` protocol first, then implemented in both backends.
- **MUST**: Tests use `SQLiteMemoryStore` (via `MIND_ALLOW_SQLITE_FOR_TESTS` fixture in `conftest.py`).

### 2.5 Contract-First Design

All primitive operations use typed Pydantic contracts (`mind/primitives/contracts.py`).
- **MUST**: `ContractModel` base class with `extra="forbid"`, `frozen=True`, `str_strip_whitespace=True`.
- **MUST**: New primitive request/response types inherit from `ContractModel`.

---

## 3. Coding Standards (MUST follow)

### 3.1 Type Safety
- **MUST**: All functions have explicit type annotations (enforced by `mypy --disallow-untyped-defs`).
- **MUST**: No `# type: ignore` without an accompanying comment explaining why.
- **MUST**: Use `from __future__ import annotations` at the top of every module.

### 3.2 Style
- Line length: 100 characters (ruff enforced).
- Import order: stdlib → third-party → local (isort via ruff `I` rule).
- String quotes: double quotes preferred.
- **MUST**: Pass `ruff check` and `mypy` with zero errors before committing.

### 3.3 Error Handling
- **MUST**: Raise domain-specific exceptions, not generic `Exception` or `RuntimeError`.
- **MUST**: App services catch domain exceptions and map them via `map_domain_error()`.
- **MUST NOT**: Silently swallow exceptions with bare `except:` or `except Exception: pass`.

### 3.4 Naming Conventions
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Enums: class `PascalCase(StrEnum)`, members `UPPER_SNAKE_CASE`
- Private: prefix with `_` (single underscore)

### 3.5 Testing
- Test files: `tests/test_<module>.py` or `tests/test_phase_<x>_<feature>.py`
- **MUST**: Every new public function/method has at least one test.
- **MUST**: Tests use SQLite in-memory store (no external dependencies).
- **MUST**: Tests are deterministic — no randomness, no network calls, no time-dependent assertions.
- Fixtures go in `tests/conftest.py` or phase-specific conftest.

### 3.6 Documentation
- Docstrings: required for all public classes and functions.
- Format: Google-style docstrings (one-liner or multi-line).
- **MUST NOT**: Add docstrings to code you did not change (avoid noise).

### 3.7 Change Scope & File Growth
- **MUST**: Shape work as the smallest viable change. If a task would touch
  more than 5 files, split it into smaller tasks unless the extra files are
  required by `CHANGE_PROTOCOL.md`.
- **MUST NOT**: Mix feature work, refactoring, and unrelated cleanup in the
  same change.
- **MUST**: If a target file is already over 400 lines, prefer extracting a
  sibling module instead of adding another responsibility to the file.
- **MUST**: If a file is already over 800 lines, only make minimal bug-fix
  edits or split it as part of the change.

---

## 4. Product Constraints (MUST respect)

- **Backward compatibility**: REST API v1 endpoints MUST NOT have breaking changes.
- **MCP tool stability**: Published MCP tool names and parameter schemas MUST NOT change without version bump.
- **CLI contract**: `mind` (product CLI) command signatures are stable. `mindtest` (dev CLI) may change.
- **No gratuitous changes**: Every change MUST relate to a user requirement or identified defect. No "refactor for fun."
- **Performance**: API responses SHOULD complete within 200ms (p95) for read operations.

---

## 5. Forbidden Patterns

- ❌ `import *` — always use explicit imports.
- ❌ Mutable default arguments in function signatures.
- ❌ Global mutable state outside `GlobalRuntimeManager`.
- ❌ Direct database access outside `mind/kernel/`.
- ❌ Adding dependencies to `[project.dependencies]` without discussion — use optional groups.
- ❌ Hardcoded secrets, API keys, or connection strings.
- ❌ `print()` for logging — use `logging.getLogger(__name__)`.
- ❌ Nested functions deeper than 2 levels.
- ❌ Files longer than 800 lines — split into modules.
- ❌ Placeholder production code (`TODO`, `FIXME`, `NotImplementedError`,
  `pass`, temporary fallback) as the final implementation.
- ❌ Circular imports — if you get one, the layering is wrong.

---

## 6. Rule Routing Table

**Before modifying code in a directory, read the corresponding rule file:**

| When you modify...              | Read this rule file first               |
|---------------------------------|-----------------------------------------|
| `mind/kernel/`                  | `.ai/rules/kernel.md`                   |
| `mind/primitives/`             | `.ai/rules/primitives.md`               |
| `mind/access/`, `mind/governance/`, `mind/capabilities/`, `mind/offline/`, `mind/workspace/` | `.ai/rules/domain-services.md` |
| `mind/app/services/`           | `.ai/rules/app-services.md`             |
| `mind/api/`                    | `.ai/rules/api.md`                      |
| `mind/mcp/`, `mind/frontend/`, `mind/cli.py`, `mind/product_cli.py` | `.ai/rules/transport.md` |
| `mind/telemetry/`              | `.ai/rules/telemetry.md`                |
| `tests/`                       | `.ai/rules/testing.md`                  |
| `alembic/versions/`           | `.ai/rules/migration.md`               |
| `docs/`                        | `.ai/rules/docs.md`                     |

---

## 7. Change Type Checklist Routing

**Before starting a change, load the matching checklist:**

| Change type                     | Checklist file                          |
|---------------------------------|-----------------------------------------|
| Add new application service     | `.ai/checklists/new-service.md`         |
| Add new REST/MCP/CLI endpoint   | `.ai/checklists/new-endpoint.md`        |
| Add new primitive operation     | `.ai/checklists/new-primitive.md`       |
| Fix a bug                       | `.ai/checklists/bug-fix.md`             |
| Refactor existing code          | `.ai/checklists/refactor.md`            |

---

## 8. Memory Object Types (Reference)

Core object types defined in `mind/kernel/schema.py`:

`RawRecord`, `TaskEpisode`, `SummaryNote`, `ReflectionNote`, `EntityNode`,
`LinkEdge`, `WorkspaceView`, `SchemaNote`, `FeedbackRecord`, `PolicyNote`,
`PreferenceNote`, `ArtifactIndex`

Valid statuses: `active`, `archived`, `deprecated`, `invalid`

Every memory object MUST have: `id`, `type`, `content`, `source_refs`,
`created_at`, `updated_at`, `version`, `status`, `priority`, `metadata`.

---

## 9. Primitive Operations (Reference)

Defined in `PrimitiveName` enum (`mind/primitives/contracts.py`):

| Primitive          | Purpose                                      |
|--------------------|----------------------------------------------|
| `WRITE_RAW`        | Store raw records into episodes               |
| `READ`             | Read objects by ID                            |
| `RETRIEVE`         | Search (keyword, time_window, vector)         |
| `SUMMARIZE`        | Generate summaries                            |
| `REFLECT`          | Episode reflection and learning               |
| `LINK`             | Create connections between objects             |
| `REORGANIZE_SIMPLE`| Archive, deprecate, reprioritize              |
| `RECORD_FEEDBACK`  | Post-query quality signals                    |

---

## 10. Self-Governance

- If you notice a rule in this file that is wrong, outdated, or missing, **flag it** to the user.
- If you follow a rule and it leads to a bad outcome, record it in `.ai/health/drift-log.md`.
- After completing any task, verify: "Did I follow the CHANGE_PROTOCOL?"

### 10.1 Health Check

This project has an automated health check script: `scripts/ai_health_check.py`.

**When to run it:**
- After completing a batch of code changes (before committing)
- After fixing bugs or refactoring
- When the user asks for a health assessment, full check, AI health test, 全面检查, 健康检测, or similar
- When you are unsure whether your changes introduced regressions

**How to run:**
```bash
uv run python scripts/ai_health_check.py --report-for-ai
```

**After running**, read the generated repair guide at `.ai/health/repair-prompt.md`.
It contains a prioritized list of violations with file locations, descriptions,
and fix hints. Follow the priority order: tests → architecture → forbidden patterns → mypy → ruff.

**Quick drift check** (no re-scan, compares last two reports):
```bash
uv run python scripts/ai_health_check.py --compare
```
