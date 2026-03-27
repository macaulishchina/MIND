# Change Proposal: Concurrent Memory Operations

## Metadata

- Change ID: `concurrent-fact-processing`
- Type: `feature`
- Status: `approved`
- Spec impact: `none` (internal execution model change, public API unchanged)
- Verification profile: `feature`
- Owner: `agent`
- Related specs: `none`

## Summary

`Memory.add()` currently processes extracted facts **serially**. With 4 facts,
the total wall-clock time is ~16s because each fact goes through
embed → search → LLM decision → execute, with ~3s per fact dominated by LLM
I/O. Since facts have **no data dependencies** between each other, they can be
processed concurrently, reducing the total time to ~max(single_fact) ≈ 3s.

This change introduces a **full concurrency architecture** for the Memory
system: a read-write separated threading model, a global thread pool with
starvation-prevention, and thread-safety fixes for all components.

## Why Now

A single `add()` call takes 12–17 seconds for a 4-fact conversation.
Over 95% of this time is I/O-bound (waiting for LLM API responses).
This is the single largest latency bottleneck in the system.

Additionally, `Memory` will be used in multi-threaded environments (Web API /
FastAPI), so all public methods must be thread-safe by design.

## In Scope

1. Full concurrency architecture (read-write separation, global write pool,
   Semaphore starvation-prevention)
2. Thread-safety fix for `SQLiteManager` (per-thread connections)
3. `[concurrency]` config section with `max_workers` and `min_available_workers`
4. `add()` internal fact parallelization as the first pool consumer
5. Ensuring all public methods are safe for concurrent external calls

## Out Of Scope

- Async/await conversion (too invasive for the current sync codebase)
- Concurrent `_extract_facts` (it's a single LLM call, no gain)
- Rate limiting / backpressure against LLM providers (deferred)
- Read-side thread pool (reads are fast, caller thread is optimal)

## Proposed Changes

### 1. Concurrency Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    External callers                      │
│  Thread-1: add(msgs, alice)     ← write, uses pool      │
│  Thread-2: add(msgs, bob)       ← write, uses pool      │
│  Thread-3: search("coffee")     ← read, caller thread   │
│  Thread-4: update(id, text)     ← write, caller thread  │
│  Thread-5: get(id)              ← read, caller thread   │
└────────┬────────┬────────┬────────┬────────┬────────────┘
         │        │        │        │        │
         ▼        ▼        │        │        │
┌────────────────────────┐ │        │        │
│  Write Thread Pool     │ │        │        │
│  (max_workers = 8)     │ │        │        │
│                        │ │        │        │
│  ┌──────────────────┐  │ │        │        │
│  │ Semaphore(6)     │  │ │        │        │
│  │ = mw - min_avail │  │ │        │        │
│  └──────────────────┘  │ │        │        │
│                        │ │        │        │
│  add-1: fact1 ─┐      │ │        │        │
│         fact2 ─┤ ║    │ │        │        │
│  add-2: fact3 ─┤ ║    │ │        │        │
│         fact4 ─┘ ║    │ │        │        │
└────────────────────────┘ │        │        │
                           │        │        │
         ┌─────────────────┘        │        │
         ▼                          ▼        ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ LLM ✅   │ │ Embedder │ │ Qdrant   │ │ SQLite   │
│ safe     │ │ ✅ safe  │ │ ✅ safe  │ │ ⚠ fix    │
└──────────┘ └──────────┘ └──────────┘ └──────────┘
```

### 2. Read-Write Separation

| Method      | R/W   | Execution model            | Needs pool? |
|-------------|-------|----------------------------|-------------|
| `add()`     | Write | Facts parallel via pool     | ✅ Yes      |
| `search()`  | Read  | Caller thread, direct      | ❌ No       |
| `get()`     | Read  | Caller thread, direct      | ❌ No       |
| `get_all()` | Read  | Caller thread, direct      | ❌ No       |
| `update()`  | Write | Caller thread, direct      | ❌ No       |
| `delete()`  | Write | Caller thread, direct      | ❌ No       |
| `history()` | Read  | Caller thread, direct      | ❌ No       |

**Why reads don't need a pool**: Read operations are single-step or two-step,
very fast, and all underlying components are thread-safe for reads. Running
in the caller's thread is optimal — zero overhead, never starved by writes.

**Why update/delete don't need a pool**: They are single-memory operations
with no internal parallelism opportunity. Thread-safe via component-level
safety.

### 3. Starvation Prevention: Semaphore Mechanism

**Problem**: A single `add()` extracting many facts could monopolize all pool
threads, starving concurrent `add()` calls.

**Solution**: A shared `Semaphore(max_workers - min_available_workers)`. Each
fact task acquires the semaphore before execution:

```python
class Memory:
    def __init__(self, ...):
        mw = config.concurrency.max_workers           # 8
        ma = config.concurrency.min_available_workers  # 2

        self._pool = ThreadPoolExecutor(max_workers=mw)
        self._call_sem = Semaphore(mw - ma)            # 6

    def add(self, ...):
        facts = self._extract_facts(...)

        def guarded_process(fact):
            self._call_sem.acquire()
            try:
                return self._process_fact(fact, ...)
            finally:
                self._call_sem.release()

        futures = [self._pool.submit(guarded_process, f) for f in facts]
        results = [f.result() for f in futures]
```

**Behavior matrix** (max_workers=8, min_available_workers=2):

| Scenario                            | Active threads | Pool remaining |
|-------------------------------------|---------------|----------------|
| 1 add, 4 facts                     | 4             | 4 idle         |
| 1 add, 10 facts                    | 6 (sem cap)   | 2 guaranteed   |
| 2 adds × 4 facts simultaneously    | ~4 each       | natural sharing|
| 2 adds × 10 facts simultaneously   | ~4 each       | sem + pool cap |

**Edge cases**:
- `min_available_workers = 0` → no protection, single add can fill pool
- `min_available_workers >= max_workers` → config validation error
- `max_workers = 1, min_available_workers = 0` → fully serial

### 4. Thread Safety Analysis

| Component         | Thread-safe? | Fix needed                               |
|-------------------|-------------|------------------------------------------|
| OpenAI SDK client | ✅ Yes       | httpx pool is thread-safe                |
| Anthropic (httpx) | ✅ Yes       | httpx.Client is thread-safe              |
| Google (httpx)    | ✅ Yes       | Same as Anthropic                        |
| QdrantClient      | ✅ Yes       | gRPC/REST clients are thread-safe        |
| SQLiteManager     | ❌ No        | Fix: `threading.local()` per-thread conn |
| Python logging    | ✅ Yes       | Handler locks are built-in               |
| generate_id()     | ✅ Yes       | uuid4() is thread-safe                   |
| get_utc_now()     | ✅ Yes       | datetime.now(UTC) is thread-safe         |

### 5. SQLiteManager Thread-Safety Fix

**Problem**: `sqlite3.Connection` objects are bound to the creating thread.

**Solution**: `threading.local()` for per-thread connection caching:

```python
import threading

class SQLiteManager:
    def __init__(self, config):
        self.db_path = config.db_path
        self._local = threading.local()
        self._ensure_table()

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn
```

SQLite handles concurrent writes from different connections via internal
file-level locking. For our write volume (< 10 writes per add()), this is
sufficient. WAL mode can be enabled later if needed.

### 6. Configuration

```toml
[concurrency]
max_workers = 8            # Write thread pool size (global)
min_available_workers = 2  # Reserved threads to prevent starvation
```

Config validation:
- `max_workers >= 1`
- `0 <= min_available_workers < max_workers`

### 7. Memory Lifecycle

```python
class Memory:
    def __init__(self, ...):
        ...
        self._pool = ThreadPoolExecutor(max_workers=...)
        self._call_sem = Semaphore(...)

    def close(self):
        """Shutdown the thread pool gracefully."""
        self._pool.shutdown(wait=True)
```

### 8. Race Conditions — Eventual Consistency

Under the **eventual consistency** model:

- **Two adds both ADD the same fact**: Acceptable. Next add() will detect
  the duplicate via similarity search and emit NONE.
- **Two adds UPDATE the same memory**: Extremely unlikely. Last-write-wins.
- **DELETE + UPDATE race**: Idempotent either way.
- **Read during write**: Reader sees pre-write or post-write state, both valid.

### 9. Logging Under Concurrency

Python's `logging` module is already thread-safe. Log lines from concurrent
facts will interleave, but each line is atomic and self-contained with enough
context (provider, model, operation, id) to be traceable. No changes needed.

## Reality Check

1. **ThreadPoolExecutor overhead**: Minimal for I/O-bound tasks (~1ms per
   thread vs ~3s per LLM call).

2. **Provider rate limits**: Concurrent requests multiply API pressure.
   With max_workers=8, up to 8 concurrent LLM calls. Manageable for most
   providers. If limits hit, reduce max_workers.

3. **SQLite under pressure**: File-level locking handles our volume fine.
   WAL mode available as a future optimization.

4. **Semaphore fairness**: Python's `threading.Semaphore` is not strictly
   FIFO, but for a few concurrent adds, practical fairness is sufficient.

5. **Alternative: asyncio**: More efficient but requires converting the
   entire chain to async. Too invasive. ThreadPoolExecutor is the right
   incremental step.

## Acceptance Signals

1. `add()` with 4 facts completes in ≤ max(single_fact_time) + 1s, not sum
2. All facts correctly processed (same decisions as serial)
3. SQLite history records written correctly under concurrency
4. No thread-safety errors, deadlocks, or data races
5. Two concurrent `add()` calls don't starve each other
6. Read operations unaffected by concurrent writes
7. `max_workers=1, min_available=0` behaves like old serial code
8. Config validation rejects invalid combinations

## Verification Plan

- Profile: `feature`
- Checks:
  - **Functional**: add() with multi-fact conversation, correct results
  - **Performance**: wall-clock time reduced ≥ 40% with ≥ 3 facts
  - **Serial equivalence**: max_workers=1 produces identical results
  - **Concurrent safety**: two simultaneous add() calls complete correctly
  - **Read isolation**: search() during add() returns valid results
  - **Error isolation**: one fact failing doesn't kill siblings
  - **Starvation**: concurrent adds share pool fairly
  - **Config validation**: invalid combos rejected at init

## Open Questions

1. ~~Should `max_workers` be configurable via `mind.toml`?~~
   **Resolved**: Yes, in `[concurrency]` section.
2. ~~Should we add a `concurrent: bool` flag to `add()`?~~
   **Resolved**: No. `max_workers=1` serves as serial mode.
3. ~~Starvation prevention mechanism?~~
   **Resolved**: Semaphore(max_workers - min_available_workers) shared by
   all add() calls.
4. ~~Read-write separation?~~
   **Resolved**: Reads in caller thread, writes (add facts) via pool.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
