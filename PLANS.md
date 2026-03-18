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
- Add the first raw-format import path so real public dataset files can be
  compiled into deterministic normalized local slices before evaluation.
- Add an end-to-end memory lifecycle benchmark that exercises real `write_raw`,
  `summarize`, `reflect`, `reorganize_simple`, `promote_schema`, and final
  `ask` flows with benchmark-phase metrics and queryable telemetry.

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
- Reuse the existing frontend debug timeline instead of inventing a second log
  viewer.
- Keep the lifecycle benchmark web surface inside the existing frontend app
  service and `/v1/frontend/*` transport family.

## Non-Goals

- Downloading full public datasets at runtime.
- Adding new transport endpoints or app services for dataset import.
- Extending the runtime access benchmark with derived mode labels in this first
  slice.
- Reworking existing internal benchmark fixtures.
- Adding a brand-new product web page just for this benchmark in the first
  iteration.

## Affected Areas

- `mind/fixtures/`
- `mind/eval/`
- `mind/app/`
- `mind/api/`
- `mind/frontend/`
- `frontend/`
- `scripts/`
- `tests/`
- `docs/`
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
7. Add a first raw-format importer and dev workflow for compiling a real
  dataset input into a normalized local slice.
8. Add a memory lifecycle benchmark runner that ingests raw events, stages
  summarize/reflect/reorganize/offline maintenance, runs final ask queries,
  and emits metrics plus telemetry-backed operation logs.
9. Add a script entrypoint and regression tests for the lifecycle benchmark.
10. Add a frontend-facing lifecycle benchmark launch/query surface through the
  existing app service, REST router, and web console.

## Verification

- `uv run ruff check mind/ tests/`
- `uv run mypy mind/ tests/`
- `uv run pytest tests/test_public_dataset_adapters.py -q --no-header`
- `uv run pytest tests/test_public_dataset_raw_import.py -q --no-header`
- `uv run pytest tests/test_memory_lifecycle_benchmark.py -q --no-header`
- `uv run pytest tests/test_phase_m_frontend_experience.py tests/test_phase_m_frontend_service.py tests/test_wp3_rest_api.py tests/test_phase_m_frontend_static.py -q --no-header`
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
- `done` — Ran the first broader public-dataset validation reports through the formal `mindtest report public-dataset ...` CLI path for local `LoCoMo`, `HotpotQA`, and `SciFact` slices, confirming the end-to-end acceptance workflow.
- `done` — Implemented raw-format importers so SciFact-, HotpotQA-, and LoCoMo-style inputs can be compiled into normalized local slices instead of being hand-written.
- `done` — Added provider-selection support (`--provider`, `--model`, `--endpoint`, `--timeout-ms`, `--retry-policy`) and strategy selection (`--strategy`) to `evaluate_public_dataset()`, CLI, and scripts so evaluations can target real LLM backends.
- `done` — Surfaced `answer_provider_configured` in reports and CLI output so operators can verify whether a selected provider actually has credentials before running expensive evaluations.
- `done` — Split `raw_import.py` (905→181 lines) into `_raw_scifact.py`, `_raw_hotpotqa.py`, `_raw_locomo.py` to satisfy the 800-line health-check rule.
- `done` — Full health check scores **100.0/100** with 0 violations. All 1236 tests pass, ruff clean, mypy clean, mkdocs --strict clean.
- `done` — Implemented an end-to-end memory lifecycle benchmark that uses real memory primitives plus offline maintenance, writes JSON reports plus SQLite/telemetry artifacts, and records benchmark telemetry that can be queried through the existing frontend debug timeline.
- `done` — Wired the lifecycle benchmark into the existing frontend app service, REST surface, and web console so operators can launch runs and reload reports directly from the UI.
- `done` — Added focused frontend/service/REST/static regressions for benchmark launch, artifact reload, and web-console exposure.

## Decisions

- The adapter layer lives under `mind/fixtures/` instead of app or transport
  layers.
- Each dataset adapter emits a common normalized fixture bundle rather than
  writing benchmark cases directly.
- The first implementation will ship with frozen sample slices for `LoCoMo`,
  `HotpotQA`, and `SciFact` to keep tests deterministic.
- The lifecycle benchmark web integration will reuse the existing frontend
  experience surface and artifact-backed JSON reports instead of introducing a
  separate benchmark transport or dashboard.

## Open Questions

- Whether a second iteration should add `AccessDepthBenchCase` derivation from
  public datasets once mode-label heuristics are agreed.
- Whether a later iteration should add asynchronous benchmark execution instead
  of the current synchronous launch + artifact reload flow.
