# Change Proposal: Test LLM Speed Hardening

## Metadata

- Change ID: `test-llm-speed-hardening`
- Type: `refactor`
- Status: `archived`
- Spec impact: `none`
- Verification profile: `refactor`
- Owner: `Codex`
- Related specs: `owner-centered-add-eval`

## Summary

- Audit repository tests and evaluation code to ensure tests that do not need real model behavior explicitly override LLM usage to `fake`.
- Add concurrency support to evaluation paths that may still be run against real LLMs so manual eval completes faster without changing metric semantics.

## Why Now

- The repository now has STL-native evaluation and broader test coverage, but some tests still rely on the default TOML contents instead of test-local fake overrides.
- Manual evaluation against real providers is still serial in the owner-centered runner, which makes exploratory validation slower than necessary.
- Tightening the test config boundary reduces accidental token spend and makes the suite more predictably local and deterministic.

## In Scope

- Audit normal tests and eval tests for whether they truly require live LLM behavior.
- Replace TOML-dependent test setup with explicit fake overrides where live model behavior is not required.
- Add concurrency support to the owner-centered evaluation runner for real-model/manual eval usage.
- Update affected test docs to reflect the hardened strategy.

## Out Of Scope

- Changing production runtime LLM behavior.
- Rewriting dataset semantics or evaluation metrics.
- Forcing all manual eval commands to use fake models when the caller explicitly wants a real provider.

## Proposed Changes

- Introduce or extend shared test helpers so tests can request a config with explicit `fake` LLM and deterministic local stores without depending on `mindt.toml` staying fake forever.
- Update test modules that currently call `ConfigManager(...).get()` directly to use the explicit fake-backed helper when they only need deterministic pipeline behavior.
- Keep unit tests that already use mocks, fakes, or patched SDK clients unchanged unless they still leak provider defaults.
- Add `--concurrency` support to `tests/eval/runners/eval_owner_centered_add.py`, mirroring the extraction runner’s ability to evaluate cases in parallel when a real provider is used.
- Preserve case result semantics and report format while only changing how quickly cases are executed.

## Reality Check

- A full-repo rewrite is probably unnecessary: most non-eval tests already use direct fakes, local stores, or patched SDK constructors instead of making real model calls.
- The current high-risk gap is not “all tests use real LLMs”; it is narrower:
  - owner-centered eval tests read `_DEFAULT_TEST_TOML` directly instead of using an explicit fake-backed helper
  - the owner-centered eval runner is serial, unlike extraction eval
- For manual eval, forcing `fake` unconditionally would be the wrong fix because it would block legitimate real-model validation. The better split is:
  - tests: explicit fake override
  - manual eval against real providers: configurable concurrency
- Parallelism should be added carefully around whole-case execution, because each case already uses isolated temp stores; this makes concurrency feasible without cross-case state contamination.

## Acceptance Signals

- Tests that do not need live model behavior no longer depend on the default TOML provider selection.
- Owner-centered eval supports concurrent case execution without changing report contents or metric definitions.
- Existing extraction eval behavior remains intact.
- Targeted regression tests continue to pass with the hardened setup.

## Verification Plan

- Profile: `refactor`
- Checks requiring evidence:
  - `workflow-integrity`
  - `change-completeness`
  - `behavior-parity`
  - `manual-review`
- Use automated pytest coverage plus runner smoke checks as evidence.

## Open Questions

- Should owner-centered eval default to serial execution for stable log ordering, with concurrency as opt-in, or should it automatically parallelize by default when multiple cases are present?

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
