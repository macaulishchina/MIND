# Tasks: Concurrent Fact Processing

## Task List

- [x] T1: Add `ConcurrencyConfig` to schema + `MemoryConfig`, `mind.toml.example`
- [x] T2: Update `mind.toml.example` with `[concurrency]` section
- [x] T3: Fix `SQLiteManager` thread safety (`threading.local()` per-thread connections)
- [x] T4: Memory concurrency architecture (ThreadPoolExecutor + Semaphore + add() refactor + close())
- [x] T5: Verify correctness and performance

## Implementation Notes

- No separate `mind/utils/concurrent.py` needed — the pool + semaphore logic
  lives directly in `Memory`, which is simpler and avoids unnecessary abstraction.
- Config validation: `min_available_workers >= max_workers` raises `ValueError` at init.
