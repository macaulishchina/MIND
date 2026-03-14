# Execution Plan

> Multi-step plan for health-check layering, pytest acceleration, timing
> instrumentation, and access benchmark optimization.

## Goal

- Make `scripts/ai_health_check.py` default to a fast quick mode while keeping
  an explicit full mode for pre-commit verification.
- Speed up routine pytest usage for AI agents and local development.
- Add durable pytest timing logs for per-phase and per-test diagnostics.
- Remove avoidable repeated work from the access benchmark.

## Why Now

- The current health check takes several minutes and `--quick` does not reduce
  runtime in practice.
- AI agents may still invoke bare `uv run pytest tests/`, which is slower than
  the desired fast local workflow.
- The access benchmark recomputes per-case baseline work multiple times.
- There is no built-in timing artifact that explains where pytest time is
  spent.

## Constraints

- Keep public product APIs unchanged.
- Preserve full-suite coverage before commit via an explicit full health check.
- Leave full pytest serial by default because current xdist runs can trigger
  timeouts in benchmark-related tests.
- Follow `.ai` governance rules and keep documentation in sync with the new
  workflow.

## Non-Goals

- Changing CI job topology.
- Enabling parallel full pytest by default.
- Refactoring unrelated user changes already present in the worktree.

## Affected Areas

- `scripts/ai_health_check.py`
- `tests/conftest.py` and targeted tests
- `mind/access/benchmark.py`
- `.ai/*` workflow rules and agent entrypoint docs

## Risks

- Pytest timing hooks must remain compatible with xdist and non-xdist runs.
- Quick-mode marker rules must exclude heavy tests without hiding important
  routine regressions.
- Health check output changes must remain readable and stable for AI use.

## Steps

1. Add the plan file and capture scope, constraints, and verification.
2. Update the health check to default to quick mode, add `--full`, and ingest
   pytest timing output.
3. Add pytest marker automation and timing hooks, plus a focused regression test
   suite for the new behavior.
4. Optimize the access benchmark by computing per-case baselines once.
5. Sync `.ai` rules, checklists, and entrypoint guidance with the new testing
   workflow.
6. Run focused tests, then run quick and full health-check verification.

## Verification

- `uv run ruff check mind/ tests/ scripts/`
- `uv run mypy mind/ tests/ scripts/`
- `uv run pytest tests/test_ai_health_check.py -q --no-header`
- `uv run pytest tests/test_access_benchmark.py -q --no-header`
- `uv run pytest tests/test_phase_j_cli_preparation.py -q --no-header -k access_benchmark`
- `uv run python scripts/ai_health_check.py --report-for-ai`
- `uv run python scripts/ai_health_check.py --full --report-for-ai`

## Progress Log

- `done` — Created plan and inspected the current health-check, pytest, and benchmark paths.
- `done` — Implemented default quick vs explicit `--full` health-check behavior and pytest timing ingestion.
- `done` — Added pytest marker automation, timing hooks, JSON timing reports, and timing regression tests.
- `done` — Optimized access benchmark baseline reuse so each case computes its baseline once.
- `done` — Updated `.ai` workflow rules, checklists, and agent entrypoint docs to prefer quick parallel pytest and require full health checks before commit.
- `done` — Verified with targeted pytest runs plus both quick and full health checks.

## Decisions

- Default health checks will run quick mode; pre-commit guidance will point to
  explicit `--full`.
- Quick pytest will use xdist with `--dist loadfile`.
- Timing output will use terminal summaries plus a structured JSON artifact.
- Full pytest remains serial by default because observed xdist runs can still
  hit timeout-sensitive benchmark/gate tests.

## Open Questions

- None at plan creation time; use this section if implementation uncovers a
  decision that cannot be safely derived from repo context.
