# Execution Plan

> Multi-step plan for implementing a reusable public-dataset adapter layer for
> benchmark validation.

## Goal

- Add a typed adapter layer that normalizes multiple public datasets into the
  repo's existing benchmark abstractions.
- Support reusable generation of retrieval cases, answer cases, and
  long-horizon sequences from a common normalized representation.
- Land an initial adapter set for `LoCoMo`, `HotpotQA`, and a small `SciFact`
  slice so public-dataset validation can start immediately.

## Why Now

- The user wants external validation beyond the frozen in-repo fixtures.
- Current benchmarks are strong, but they are mostly based on internal synthetic
  fixtures, so they do not provide enough confidence about complex real-world
  behavior.
- Without a shared adapter layer, each public dataset would require custom one-
  off mapping logic, which would be hard to maintain and compare.

## Constraints

- Keep public product APIs unchanged.
- Do not add runtime dependencies to `[project.dependencies]`.
- Keep the change deterministic and offline-testable; no network access in
  tests.
- Reuse existing fixture dataclasses and benchmark runners where possible.
- Preserve stable IDs, case alignment, and manifest hashing semantics.

## Non-Goals

- Downloading full public datasets at runtime.
- Adding new transport endpoints or app services for dataset import.
- Extending the runtime access benchmark with derived mode labels in this first
  slice.
- Reworking existing internal benchmark fixtures.

## Affected Areas

- `mind/fixtures/`
- `tests/`
- `PLANS.md`

## Risks

- Poor ID or timestamp normalization could make public fixtures nondeterministic.
- Mismatched gold-label granularity could weaken retrieval or long-horizon
  metrics.
- Overfitting the adapter design to one dataset could make the abstraction fail
  for the next dataset.
- Manifest hashing must remain stable across repeated runs.

## Steps

1. Define the shared adapter contracts, registry, compiler helpers, and module
   boundaries.
2. Implement dataset adapters for `LoCoMo`, `HotpotQA`, and `SciFact` using
   frozen in-repo sample slices.
3. Add public builder functions that compile normalized bundles into retrieval,
   answer, and long-horizon benchmark outputs.
4. Export the new public dataset fixture surface from `mind.fixtures`.
5. Add deterministic tests for registry behavior, object validity, case
   alignment, and manifest stability.
6. Run focused tests, linting, typing, and the quick health check.

## Verification

- `uv run ruff check mind/ tests/`
- `uv run mypy mind/ tests/`
- `uv run pytest tests/test_public_dataset_adapters.py -q --no-header`
- `uv run pytest tests/test_phase_d_smoke.py tests/test_long_horizon_eval.py -q --no-header`
- `uv run python scripts/ai_health_check.py --report-for-ai`

## Progress Log

- `done` — Read `.ai/CONSTITUTION.md` plus the relevant testing and domain-service rules.
- `done` — Inspected existing fixture builders, long-horizon manifests, and benchmark alignment patterns.
- `done` — Implemented the reusable public-dataset adapter package, shared contracts, compiler helpers, and registry surface.
- `done` — Added deterministic `LoCoMo`, `HotpotQA`, and `SciFact` sample adapters plus public fixture exports.
- `done` — Added focused adapter tests covering registry behavior, schema validity, case alignment, query-mode coverage, and manifest stability.
- `done` — Added deterministic local-source slice loading so public dataset fixtures can be built from local JSON files instead of only in-repo sample builders.
- `done` — Added regression coverage for local-source loading, case alignment, deterministic manifests, and clear failure handling for broken object refs.
- `done` — Added a unified public-dataset evaluation module that summarizes retrieval, answer, and long-horizon behavior for built-in or local-source fixtures.
- `done` — Added a dev script entrypoint for running public-dataset evaluation and writing JSON reports.
- `done` — Validated the new unified evaluation entrypoint and formalized it as a first-class CLI report command for pre-validation workflows.
- `doing` — Preparing the first broader public-dataset validation runs now that adapter, loader, evaluation, and CLI report entrypoints are all in place.

## Decisions

- The adapter layer lives under `mind/fixtures/` instead of app or transport
  layers.
- Each dataset adapter emits a common normalized fixture bundle rather than
  writing benchmark cases directly.
- The first implementation will ship with frozen sample slices for `LoCoMo`,
  `HotpotQA`, and `SciFact` to keep tests deterministic.

## Open Questions

- Whether a second iteration should add `AccessDepthBenchCase` derivation from
  public datasets once mode-label heuristics are agreed.
