# Checklist: Bug Fix

Use this checklist when fixing a bug.

---

## Investigation

- [ ] Reproduce the bug with a test (write a failing test FIRST)
- [ ] Identify the root cause (not just the symptom)
- [ ] Check if the bug exists in related code paths

## Fix

- [ ] Make the minimal change to fix the root cause
- [ ] Do NOT refactor surrounding code in the same change
- [ ] Do NOT add unrelated improvements

## Testing

- [ ] The failing test now passes
- [ ] Add regression test if the bug could recur
- [ ] `uv run pytest tests/ -x` — full suite still passes (no regressions)

## Verification

- [ ] `uv run ruff check mind/ tests/` — zero errors
- [ ] `uv run mypy mind/ tests/` — zero errors
- [ ] Fix is backward-compatible (no API/CLI/MCP changes unless the bug IS in the interface)
- [ ] If the bug was in a kernel method, verify both SQLite and PostgreSQL paths

## Documentation

- [ ] If the bug revealed a missing rule, update `.ai/` rules
- [ ] If the bug revealed a documentation error, fix the docs
