# Execution Plan

> Multi-step plan for health-check layering, pytest acceleration, timing
> instrumentation, access benchmark optimization, and slow-test decomposition.

## Goal

- Keep `scripts/ai_health_check.py` fast and readable for local and full
  verification.
- Speed up routine pytest usage for AI agents and local development.
- Add durable pytest timing logs for per-phase and per-test diagnostics.
- Remove avoidable repeated work from the access benchmark.
- Break up any single test case that still takes more than 10 seconds unless
  the case is already the smallest meaningful operation and the runtime is
  inherent to that operation.

## Why Now

- The current health check takes several minutes and `--quick` does not reduce
  runtime in practice.
- AI agents may still invoke bare `uv run pytest tests/`, which is slower than
  the desired fast local workflow.
- Some AI-facing verification guidance still suggests running both the default
  quick health check and `--full` for the same milestone, which wastes time.
- The access benchmark recomputes per-case baseline work multiple times.
- There is no built-in timing artifact that explains where pytest time is
  spent.
- Full health-check timing still shows several single tests over 10 seconds,
  which blocks the desired fine-grained parallelism and makes stalls harder to
  diagnose.

## Constraints

- Keep public product APIs unchanged.
- Preserve full-suite coverage before commit via an explicit full health check.
- Preserve the behavioral quality bar of the existing gate and benchmark tests;
  splitting tests must not turn real evaluations into mock-only coverage.
- Prefer splitting public evaluation entrypoints into smaller verifiable phases
  over hiding expensive work in collection or fixture side effects.
- Follow `.ai` governance rules and keep documentation in sync with the new
  workflow.

## Non-Goals

- Changing CI job topology.
- Refactoring unrelated user changes already present in the worktree.
- Rewriting benchmark algorithms whose runtime is genuinely inherent and
  already minimal.

## Affected Areas

- `scripts/ai_health_check.py`
- `scripts/ai_health_progress.py`
- `tests/conftest.py` and targeted tests
- `mind/access/benchmark.py`
- `mind/access/gate.py`
- `mind/eval/benchmark_gate.py`
- `mind/eval/strategy_gate.py`
- `.ai/*` workflow rules and agent entrypoint docs

## Risks

- Pytest timing hooks must remain compatible with xdist and non-xdist runs.
- Quick-mode marker rules must exclude heavy tests without hiding important
  routine regressions.
- Health check output changes must remain readable and stable for AI use.
- Decomposing gate evaluations into smaller public phases can accidentally
  weaken the integration signal if the orchestration path is left untested.
- Benchmark and strategy helpers must not introduce circular imports or break
  existing JSON report contracts.

## Steps

1. Add the plan file and capture scope, constraints, and verification.
2. Update the health check to default to quick mode, add `--full`, and ingest
   pytest timing output.
3. Add pytest marker automation and timing hooks, plus a focused regression test
   suite for the new behavior.
4. Optimize the access benchmark by computing per-case baselines once.
5. Sync `.ai` rules, checklists, and entrypoint guidance with the new testing
   workflow.
6. Split or refactor slow gate and benchmark tests so each single test case
   stays under 10 seconds when the work can be decomposed without lowering the
   quality bar.
7. Run focused tests, then run quick and full health-check verification.

## Verification

- `uv run ruff check mind/ tests/ scripts/`
- `uv run mypy mind/ tests/ scripts/`
- `uv run pytest tests/test_ai_health_check.py -q --no-header`
- `uv run pytest tests/test_access_benchmark.py -q --no-header`
- `uv run pytest tests/test_phase_j_cli_preparation.py -q --no-header -k access_benchmark`
- `uv run pytest tests/test_phase_i_gate.py tests/test_phase_f_gate.py tests/test_phase_f_comparison.py tests/test_phase_g_gate.py tests/test_phase_g_deep_audit.py tests/test_access_benchmark.py tests/test_phase_j_cli_preparation.py -q --no-header`
- Local iteration: `uv run python scripts/ai_health_check.py --report-for-ai`
- Final verification: `uv run python scripts/ai_health_check.py --full --report-for-ai` (skip quick if you are already running full)

## Progress Log

- `done` — Created plan and inspected the current health-check, pytest, and benchmark paths.
- `done` — Implemented default quick vs explicit `--full` health-check behavior and pytest timing ingestion.
- `done` — Added pytest marker automation, timing hooks, JSON timing reports, and timing regression tests.
- `done` — Optimized access benchmark baseline reuse so each case computes its baseline once.
- `done` — Updated `.ai` workflow rules, checklists, and agent entrypoint docs to prefer quick parallel pytest and require full health checks before commit.
- `done` — Verified with targeted pytest runs plus both quick and full health checks.
- `done` — Followed up the AI-facing guidance so final verification uses
  `--full` instead of redundantly asking for quick plus full in the same step.
- `done` — Split the health-check progress renderer into
  `scripts/ai_health_progress.py` and excluded the health-check self-tests from
  the health-check pytest stage.
- `done` — Removed repeated expensive gate work from the existing phase I, F,
  and CLI benchmark tests by reusing real evaluation results inside each file.
- `done` — Decomposed the remaining slow gate and benchmark tests into smaller
  real evaluation slices, then kept iterating until full-mode slow tests fell
  below 5 seconds.
- `done` — Split the phase C primitive gate into tag-based slices so smoke,
  budget, rollback, and general schema/log coverage no longer share one
  oversized test.
- `done` — Split phase F comparison and ablation checks by long-horizon family
  where the per-family threshold holds, and used lighter interval-presence
  checks where the full-suite threshold is not meaningful per family.
- `done` — Separated strategy cost-report JSON round-trip coverage from the
  expensive real report evaluation so serialization tests no longer rerun the
  benchmark.
- `done` — Added file-weighted `xdist --dist loadfile` scheduling backed by the
  persisted pytest timing log, plus CLI health-check reporting for the active
  scheduler mode.
- `done` — Split remaining access benchmark, phase I, phase F, and phase G hot
  spots into smaller family, mode, episode, and sequence chunks while keeping
  real benchmark coverage.
- `done` — Corrected the default pytest worker count to follow the repo's
  `max(4, cpu_count)` rule instead of oversubscribing the machine, which
  removed the full-suite parallel slowdown that had been inflating slow-test
  timings.
- `done` — Verified the final state with focused pytest/ruff/mypy runs and two
  consecutive `--full` health checks using `loadfile(weighted)`.

## Decisions

- Default health checks will run quick mode; pre-commit guidance will point to
  explicit `--full`.
- Quick pytest will use xdist with `--dist loadfile`.
- Timing output will use terminal summaries plus a structured JSON artifact.
- Full pytest now defaults to parallel execution, with `--serial` available for
  forced single-thread runs.
- Parallel pytest worker count now follows `max(4, cpu_count)` so health checks
  stay concurrent without oversubscribing smaller local machines.
- When a slow public evaluation can be decomposed, prefer exposing smaller
  public phases and testing those phases directly rather than hiding the cost in
  module import time or oversized fixtures.

## Open Questions

- None at plan creation time; use this section if implementation uncovers a
  decision that cannot be safely derived from repo context.
