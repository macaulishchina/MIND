# Change Proposal: Owner-Centered Add Evaluation

## Metadata

- Change ID: `owner-centered-add-eval`
- Type: `feature`
- Status: `complete`
- Spec impact: `update required`
- Verification profile: `feature`
- Owner: `Codex`
- Related specs: `memory-add-extraction`, `owner-centered-memory`

## Summary

- Add a new evaluation runner and dataset shape for the owner-centered `Memory.add()` flow so the repository can measure owner resolution, subject normalization, canonical text persistence, and update behavior end-to-end.

## Why Now

- The repository now has an owner-centered add pipeline, but the only dedicated evaluation runner still targets extraction output alone.
- Without an integration-grade eval path, regressions in `subject_ref`, canonical text generation, or single-value updates can slip through even when extraction-only metrics look healthy.

## In Scope

- Add a new owner-centered add dataset format under `tests/eval/datasets/`.
- Add a new evaluation runner under `tests/eval/runners/`.
- Measure end-to-end add outcomes including owner identity reuse, subject refs, canonical text, active-memory shape, and update behavior.
- Add tests for the new runner and sample dataset behavior.
- Update evaluation docs to explain when to use extraction eval versus owner-centered add eval.

## Out Of Scope

- New runtime memory behavior beyond what is needed to exercise the existing owner-centered pipeline.
- A fully generalized retrieval benchmark for owner-centered memory quality.
- External LLM cost optimization or batch evaluation changes beyond reusing existing config structure.

## Proposed Changes

- Introduce `eval_owner_centered_add.py` that executes multi-turn owner-centered add cases against `Memory.add()` using the configured runtime stack.
- Define dataset cases with owner context, ordered turns, and expected final active memories.
- Report metrics for canonical-text accuracy, subject-ref accuracy, active-memory count accuracy, update/version behavior, and case pass rate.
- Keep extraction eval independent; the new runner complements it instead of replacing it.

## Reality Check

- A pure extraction runner cannot validate owner-centered requirements because `subject_ref` and update semantics only emerge after normalization, retrieval, and execution.
- A full end-to-end runner against real external LLMs may be noisy and costly. The baseline runner should therefore work cleanly with `mindt.toml` and fake backends first, while remaining usable with real configs when desired.
- The new runner should avoid coupling to private storage internals more than necessary. It should prefer public `Memory` methods and only read additional state when the public API cannot express the expectation.

## Acceptance Signals

- The repo can run a dedicated owner-centered add evaluation command analogous to extraction eval.
- The runner can verify self facts, named third-party facts, unnamed placeholders, anonymous owners, and single-value update behavior.
- The runner produces a JSON report plus human-readable summary consistent with the existing evaluation style.

## Verification Plan

- Profile: `feature`
- Checks:
  - `workflow-integrity`
  - `runner-behavior`
  - `dataset-shape`
  - `docs-alignment`

## Open Questions

- None blocking implementation. The user explicitly requested the evaluation path, and the existing owner-centered runtime already defines the target behavior.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
