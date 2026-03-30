# Change Proposal: Owner-Centered Relationship Dataset

## Metadata

- Change ID: `owner-centered-relationship-dataset`
- Type: `feature`
- Status: `complete`
- Spec impact: `none`
- Verification profile: `feature`
- Owner: `Codex`
- Related specs: `owner-centered-add-eval`, `owner-centered-memory`

## Summary

- Add a dedicated owner-centered relationship dataset with at least 50 evaluation cases, plus the supporting docs and regression coverage needed to run it confidently.

## Why Now

- The current owner-centered add datasets cover baseline behavior, but they are still too small and too mixed to stress relationship-centric extraction and normalization at useful depth.
- The user explicitly wants a dataset focused on owner-centered relationship cases rather than generic add coverage.

## In Scope

- Add a new dataset file under `tests/eval/datasets/` with 50+ owner-centered relationship cases.
- Focus the cases on relationship-heavy owner-centered inputs: named third parties, relation aliases, inverse relation phrasing, unnamed placeholders, multi-turn reuse, and relation-scoped separation.
- Update `tests/eval/README.md` with a manual command for the new dataset.
- Add or update tests so the new dataset is at least validated for shape and representative runner behavior.

## Out Of Scope

- Changing `Memory.add()` behavior or fake-LLM normalization semantics.
- Redesigning the owner-centered evaluation runner.
- Adding a new verification metric or changing the approved evaluation spec.

## Proposed Changes

- Introduce `tests/eval/datasets/owner_centered_relationship_cases.json`.
- Ensure the dataset contains at least 50 cases covering owner-centered relationship extraction and normalization patterns.
- Keep the dataset aligned with current owner-centered runtime semantics so it can be executed deterministically with `mindt.toml`.
- Extend docs and tests so the dataset is discoverable and exercised.

## Reality Check

- A large relationship-focused dataset is only useful if it matches current runner semantics. Cases that require unsupported entity resolution or unsupported predicate normalization would create noisy failures instead of useful signal.
- The current fake normalization backend only recognizes a bounded set of relations and predicates. The dataset should intentionally lean into those supported patterns so baseline verification remains deterministic.
- Running 50+ end-to-end cases inside a unit test would add avoidable cost; full-dataset validation should remain a manual/runner verification step, while pytest covers dataset presence and representative samples.

## Acceptance Signals

- The repo contains a dedicated owner-centered relationship dataset with at least 50 cases.
- The dataset is documented in `tests/eval/README.md`.
- The new dataset can be executed successfully through `eval_owner_centered_add.py` with `mindt.toml`.

## Verification Plan

- Profile: `feature`
- Checks:
  - `workflow-integrity`
  - `dataset-shape`
  - `runner-behavior`
  - `docs-alignment`

## Open Questions

- None blocking. The requested direction is clear, and the main implementation choice is to align the dataset with current supported owner-centered relation patterns.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
