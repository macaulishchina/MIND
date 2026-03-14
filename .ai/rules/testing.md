# Rules: Testing (`tests/`)

> Load this file when writing or modifying tests.

---

## Structure

```
tests/
├── conftest.py                    # Shared fixtures (MIND_ALLOW_SQLITE_FOR_TESTS autouse)
├── test_<feature>.py              # Feature-specific tests
├── test_phase_<x>_<feature>.py    # Phase gate tests
└── ...
```

## Rules

1. **SQLite only**: All unit tests use `SQLiteMemoryStore` with `tmp_path`.
   The autouse fixture in `conftest.py` sets `MIND_ALLOW_SQLITE_FOR_TESTS=1`.

2. **Deterministic**: No randomness, no network calls, no system clock in
   assertions. Use fixed timestamps and deterministic data.

3. **Independent**: Each test function MUST work in isolation. No test ordering
   dependencies. Every test creates its own store.

4. **Naming**: `test_<feature>_<expected_behavior>`. Be descriptive.

5. **Standard pattern**:
   ```python
   def test_feature_does_thing(tmp_path: Path) -> None:
       """Verify that feature produces expected outcome."""
       with SQLiteMemoryStore(str(tmp_path / "test.sqlite3")) as store:
           service = build_service(store)
           result = service.method(build_request({...}))
       assert result.status == AppStatus.OK
   ```

6. **One concern per test**: Test one logical behavior. Multiple asserts are OK
   if they all validate the same outcome.

7. **Test public API**: Test service methods and public functions. Don't test
   private helpers directly unless they have complex logic.

8. **Fixtures**: Put shared fixtures in `conftest.py`. Phase-specific helpers
   can live alongside the test file.

9. **Coverage**: Every new public function/method MUST have at least one test.
   New files MUST have a corresponding test file.

10. **No mocking kernel**: Don't mock the store — use the real `SQLiteMemoryStore`.
    Only mock external dependencies (LLM providers, network).

## Test Data Helpers

- `mind/fixtures/` contains canonical seed data and benchmark datasets.
- Use `mind.fixtures` to load golden test data when testing evaluation logic.

## Preferred Commands

- For routine local regression, prefer parallel quick pytest instead of bare
  `uv run pytest tests/`.
- Use worker count `max(4, cpu_count)` and `--dist loadfile` for routine
  multi-file runs. Example:
  ```bash
  uv run pytest tests/ -n "$(uv run python -c 'import os; print(max(4, os.cpu_count() or 1))')" --dist loadfile -m "not slow and not gate"
  ```
- For focused files or nodeids, keep the same worker-count rule when parallel
  execution is still helpful.
- Before committing, run `uv run python scripts/ai_health_check.py --full --report-for-ai`.

## Phase Gate Tests

- `test_phase_<x>_*.py` files are gate validation tests.
- They run specific benchmark suites and produce gate results.
- Do not modify phase gate tests without understanding the gate criteria.
