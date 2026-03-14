# MIND Coding Conventions

> Extracted from pyproject.toml, ruff/mypy config, and codebase patterns.

---

## 1. Tooling Configuration

| Tool   | Config source     | Key settings                                         |
|--------|-------------------|------------------------------------------------------|
| Ruff   | `pyproject.toml`  | line-length=100, target=py312, rules: E,F,I,B,UP     |
| MyPy   | `pyproject.toml`  | disallow_untyped_defs=true, no_implicit_optional=true |
| Pytest | `pyproject.toml`  | testpaths=["tests"], python_files=["test_*.py"]       |

Run before committing:
```bash
uv run ruff check mind/ tests/ scripts/
uv run ruff format --check mind/ tests/ scripts/
uv run mypy mind/ tests/ scripts/
uv run python scripts/ai_health_check.py --full --report-for-ai
```

Routine local pytest should prefer the parallel quick command from
`.ai/rules/testing.md` instead of bare `uv run pytest tests/`.
If you are already running the pre-commit full health check, skip a separate
quick health check for that same verification step.

---

## 2. File Organization

### Module structure
```
mind/<module>/
├── __init__.py      # Public exports (keep minimal)
├── service.py       # Service class with public API
├── contracts.py     # Pydantic request/response models
└── <internals>.py   # Private implementation modules
```

### Import conventions
```python
from __future__ import annotations    # ALWAYS first line

# stdlib
import logging
from datetime import UTC, datetime

# third-party
from pydantic import Field

# local — always relative within the same package
from mind.kernel.store import MemoryStore
from mind.primitives.contracts import ContractModel
```

---

## 3. Pydantic Model Conventions

```python
class MyModel(ContractModel):
    """One-line description."""
    
    field_name: str = Field(min_length=1)
    optional_field: str | None = None
    list_field: list[str] = Field(default_factory=list)
```

Rules:
- Inherit from `ContractModel` (gives `extra="forbid"`, `frozen=True`).
- Use `X | None` syntax, not `Optional[X]` (enforced by UP rules in ruff).
- Required fields first, optional fields last.
- Use `Field()` for validation constraints.

---

## 4. Enum Conventions

```python
class MyEnum(StrEnum):
    """Short description."""
    
    VALUE_ONE = "value_one"
    VALUE_TWO = "value_two"
```

- Always inherit from `StrEnum` (not `Enum`).
- Member names: `UPPER_SNAKE_CASE`.
- Member values: `lower_snake_case` strings (matches JSON serialization).

---

## 5. Service Class Conventions

```python
class MyService:
    """One-line description of what this service does."""

    def __init__(
        self,
        store: MemoryStore,
        *,
        capability_service: CapabilityService | None = None,
        telemetry_recorder: TelemetryRecorder | None = None,
    ) -> None:
        self._store = store
        self._capability_service = capability_service
        self._telemetry = telemetry_recorder
```

Rules:
- Required deps are positional args; optional deps are keyword-only.
- Store private references with `_` prefix.
- Keep `__init__` free of side effects.

---

## 6. App Service Method Conventions

```python
def do_something(self, req: AppRequest) -> AppResponse:
    """One-line description."""
    if self._request_defaults_resolver is not None:
        req = self._request_defaults_resolver(req, ...)
    resp = new_response(req)
    ctx = resolve_execution_context(req.principal, req.session, req.policy, req.provider_selection)
    
    try:
        result = self._primitive.some_operation(data, ctx)
    except Exception as exc:
        resp.status = AppStatus.ERROR
        resp.error = map_domain_error(exc)
        return resp

    resp.status = result_status(result)
    resp.result = {...}
    return resp
```

---

## 7. Logging Conventions

```python
import logging

_log = logging.getLogger(__name__)

# Usage
_log.info("Processing %s items", count)         # Lazy formatting
_log.debug("Detailed state: %r", state_dict)     # Debug only
_log.warning("Unexpected condition: %s", detail)  # Warnings
_log.exception("Failed to process")               # With traceback
```

- Never use `print()`.
- Never use f-strings in log calls (use `%s` lazy formatting).
- Module-level `_log = logging.getLogger(__name__)`.

---

## 8. Test Conventions

```python
def test_feature_does_expected_thing(tmp_path: Path) -> None:
    """Verify that <feature> produces <expected outcome>."""
    with SQLiteMemoryStore(str(tmp_path / "test.sqlite3")) as store:
        service = MyService(store)
        result = service.do_something(build_request({...}))
    
    assert result.status == AppStatus.OK
    assert result.result["key"] == expected_value
```

- Test function names: `test_<feature>_<expected_behavior>`
- One assertion focus per test (multiple asserts are OK if validating one logical outcome).
- Use `tmp_path` fixture for file-based tests.
- Use `SQLiteMemoryStore` — never PostgreSQL in unit tests.

---

## 9. Memory Object Construction

```python
obj = {
    "id": f"obj-{uuid4().hex[:16]}",
    "type": "RawRecord",
    "content": "...",
    "source_refs": [...],
    "created_at": datetime.now(UTC).isoformat(),
    "updated_at": datetime.now(UTC).isoformat(),
    "version": 1,
    "status": "active",
    "priority": 0.5,
    "metadata": {
        "record_kind": "observation",
        "episode_id": "...",
        "timestamp_order": 1,
    },
}
```

- Always use UTC timestamps.
- All required fields must be present (see `mind/kernel/schema.py` REQUIRED_FIELDS).
- Type-specific metadata fields must be present (see REQUIRED_METADATA_FIELDS).

---

## 10. Git Conventions

- Commit messages: `<type>: <short description>` (feat, fix, refactor, docs, test, ci)
- Branch naming: `<type>/<short-description>` (feature/add-tags-endpoint)
- One logical change per commit.
