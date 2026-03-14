# Checklist: Adding a New Primitive

Use this checklist when adding a new primitive operation to `mind/primitives/`.

---

## Pre-work

- [ ] Read `.ai/rules/primitives.md`
- [ ] Read `.ai/rules/kernel.md` (if new store methods needed)
- [ ] Define the primitive's purpose in one sentence
- [ ] Confirm it doesn't overlap with existing primitives

## Contracts

- [ ] Add member to `PrimitiveName` enum in `mind/primitives/contracts.py`
- [ ] Define request model (inherits `ContractModel`)
- [ ] Define response model (inherits `ContractModel`)
- [ ] Add any new error codes to `PrimitiveErrorCode`

## Implementation

- [ ] Add method to `PrimitiveService` in `mind/primitives/service.py`
- [ ] Record `BudgetEvent` for cost tracking
- [ ] Record `PrimitiveCallLog`
- [ ] Use telemetry recorder for observability
- [ ] Handle errors with proper `PrimitiveErrorCode`

## Store (if needed)

- [ ] Add method to `MemoryStore` protocol in `mind/kernel/store.py`
- [ ] Implement in `SQLiteMemoryStore`
- [ ] Implement in `PostgresMemoryStore`
- [ ] Create Alembic migration if schema changes needed

## Error Mapping

- [ ] Map new `PrimitiveErrorCode` values to `AppErrorCode` in `mind/app/errors.py`

## Testing

- [ ] Create `tests/test_<primitive_name>.py`
- [ ] Test happy path
- [ ] Test budget/capability validation
- [ ] Test error conditions
- [ ] Use SQLite store, deterministic data

## Verification

- [ ] `uv run ruff check mind/ tests/` — zero errors
- [ ] `uv run mypy mind/ tests/` — zero errors
- [ ] `uv run pytest tests/ -x` — all pass
