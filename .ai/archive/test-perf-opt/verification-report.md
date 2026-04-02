# Verification Report: test-perf-opt

## Change ID: `test-perf-opt`

## Profile: `quick`

## Results

| Check | Status | Evidence |
|-------|--------|----------|
| All 190 tests pass | ✅ PASS | 3 consecutive runs: 190 passed |
| Wall-clock ≤ 30s | ✅ PASS | 11.99s / 12.99s / 13.32s (avg ~12.8s) |
| No flakiness | ✅ PASS | 3 runs, 0 failures |
| No test removed or weakened | ✅ PASS | Same 190 tests, same assertions |

## Baseline vs Optimized

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Wall-clock time | 58.64s | ~12.8s | **4.6x faster** |
| Tests passing | 190/190 | 190/190 | No change |

## Changes Made

1. **Added `pytest-xdist`** to `requirements.txt` — enables multi-process
   parallel test execution.

2. **Created `pytest.ini`** with `addopts = -n auto --dist loadgroup -q` —
   automatically uses all available CPU cores for parallel test execution.

3. **Optimized `SQLiteSTLStore.seed_vocab()`** in `mind/stl/store.py` —
   replaced 85 individual INSERT+COMMIT calls with a single `executemany`
   + one COMMIT. This reduced file-backed SQLite initialization from
   ~1.2s to ~0.24s per instance (5x faster). This was the dominant
   bottleneck since eval tests create many Memory instances, each
   constructing a new STL store.

## Notes

- The `seed_vocab` optimization is a production-code improvement (not
  test-only), but it's a pure performance fix with no behavioral change.
  The same 85 vocab entries are inserted with the same ON CONFLICT logic.
- `pytest-xdist` parallelism works cleanly because tests already use
  `tmp_path` for isolated DB files and in-memory Qdrant per process.
