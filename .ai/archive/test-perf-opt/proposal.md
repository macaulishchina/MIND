# Change Proposal: Optimize pytest suite to ≤ 30s

## Metadata

- Change ID: `test-perf-opt`
- Type: `refactor`
- Status: `complete`
- Spec impact: `none`
- Verification profile: `quick`
- Owner: `agent`
- Related specs: `none`

## Summary

- Optimize `pytest tests/` execution from ~59s to ≤ 30s without sacrificing
  test scope or quality.

## Why Now

- `pytest tests/` is run frequently during development. At ~59s per run it
  slows the iteration loop significantly. Halving this improves developer
  productivity.

## In Scope

- Test-side configuration and fixture optimization.
- `pytest-xdist` parallel execution across worker processes.
- Reducing redundant `Memory` instance construction in eval tests.
- Conftest-level session-scoped fixtures where safe.

## Out Of Scope

- Changing production code behavior.
- Removing or weakening any existing test assertion.
- Adding new tests (other than verifying the speed target).

## Proposed Changes

### 1. Install `pytest-xdist` and configure parallel workers

Add `pytest-xdist` to dev dependencies. Configure `pytest.ini` /
`pyproject.toml` with `-n auto` (or a fixed worker count) so tests run
in parallel across CPU cores.

### 2. Reduce per-test Memory construction overhead in eval tests

The top 3 slowest tests (`test_owner_add_report_and_summary_render` at
19.6s, `test_owner_add_dataset_concurrency_preserves_case_order` at 16.0s,
`test_owner_add_representative_cases_pass` at 6.0s) all construct a fresh
`Memory` instance per eval case inside `_evaluate_owner_add_case`.

These tests already use the `memory_config` fixture which forces `fake`
LLM providers and in-memory Qdrant. The bottleneck is the repeated
`Memory.__init__` (QdrantClient, ThreadPoolExecutor, embedder, stores).

We will **not** share Memory instances across tests (isolation is important),
but we can let pytest-xdist distribute these independent heavy tests across
workers so they run in parallel.

### 3. Ensure test isolation under parallel execution

Each test already uses `tmp_path` for DB files and unique collection names.
In-memory Qdrant is per-process. No shared mutable state is expected.

## Reality Check

- `pytest-xdist` spawns separate processes, so the GIL is not a concern.
  Each worker gets its own in-memory Qdrant, SQLite, etc.
- With 4+ CPU cores available, distributing ~190 tests across workers
  should cut wall-clock time roughly proportionally.
- The three slowest tests (19.6s, 16.0s, 6.0s) will still take their full
  time in whichever worker runs them, so a single-worker lower bound is
  ~20s. With 4 workers the theoretical best is ~15s.
- Risk: if any test has hidden global state (singleton patterns, module-level
  caches), parallel execution could surface flaky failures. This will be
  validated by running the full suite multiple times under `-n auto`.
- If xdist alone is insufficient, we can additionally optimize the
  multi-case eval tests by caching/reusing the Memory config construction
  within a single test function (the per-case `_eval_config` already creates
  isolated stores, so config construction could be lifted).

## Acceptance Signals

- `pytest tests/` completes in ≤ 30s wall-clock time.
- All 190 tests still pass.
- No test removed or assertion weakened.

## Verification Plan

- Profile: `quick`
- Run `time .venv/bin/python -m pytest tests/` and confirm ≤ 30s.
- Run it 3 times to check for flakiness.

## Open Questions

- Preferred number of workers: `auto` (CPU count) or a fixed number?
  → Will start with `auto` and adjust if needed.

## Approval

- [ ] Proposal reviewed
- [ ] Important conflicts and feasibility risks surfaced
- [ ] Spec impact confirmed
- [ ] Ready to finalize tasks and implement
