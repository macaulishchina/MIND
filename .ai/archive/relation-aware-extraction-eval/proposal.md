# Change Proposal: Relation-Aware Extraction Eval

## Metadata

- Change ID: `relation-aware-extraction-eval`
- Type: `feature`
- Status: `approved`
- Spec impact: `update required`
- Verification profile: `feature`
- Owner: `Codex`
- Related specs: `memory-add-extraction`

## Summary

- Upgrade `tests/eval/runners/eval_extraction.py` so it can evaluate relationship-focused extraction behavior while staying backward compatible with existing non-relationship extraction cases, then replace the fragmented legacy extraction datasets with one curated 100-case general dataset plus one 100-case relationship-only dataset.

## Why Now

- The current extraction eval runner only scores generic fact extraction and has no explicit way to measure relation-heavy extraction quality.
- The current extraction dataset topology is fragmented across easy/medium/hard/tricky plus a separate blackbox holdout, which no longer matches the desired workflow.
- The user explicitly wants to focus on LLM extraction quality for relation-bearing inputs rather than end-to-end owner-centered add results.

## In Scope

- Extend `eval_extraction.py` with optional relationship-aware annotations and reporting while preserving support for old case shapes.
- Consolidate the existing extraction datasets, including blackbox content, into a single curated 100-case general extraction dataset.
- Add a second 100-case extraction dataset dedicated to relation-heavy inputs and coverage.
- Remove obsolete extraction dataset files that the new curated datasets replace.
- Update docs and regression tests accordingly.

## Out Of Scope

- Changing runtime extraction behavior in `Memory._extract_facts()`.
- Changing owner-centered add runtime behavior or normalization logic.
- Reworking `eval_owner_centered_add.py`.

## Proposed Changes

- Add optional relation annotations to extraction eval cases and compute relationship-oriented metrics without breaking existing case files.
- Curate a single 100-case general extraction dataset from the current top-level extraction and blackbox sources, dropping low-value trivial cases.
- Add a comprehensive 100-case relation-only extraction dataset that stresses relation aliases, inverse phrasing, named vs unnamed third parties, multilingual inputs, negative/no-extract cases, and multi-fact relation extraction.
- Update README and evolution docs so manual evaluation points to the new curated datasets.

## Reality Check

- Extraction-stage evaluation only sees free-text extracted facts, not structured relation objects. So relation-aware scoring must operate on relation signals observable in extracted text instead of pretending normalization already happened.
- Fully deleting the old datasets is safe only if docs, tests, and default dataset discovery are updated together; otherwise the runner and existing guidance will drift.
- Running all 200 curated extraction cases inside unit tests would be unnecessarily heavy. Full-dataset verification should remain a runner command, while pytest covers the relation-aware logic and dataset presence.

## Acceptance Signals

- `eval_extraction.py` accepts relation-aware annotations without breaking legacy datasets.
- The repo contains exactly two maintained extraction datasets: one curated general set with 100 cases and one relation-only set with 100 cases.
- The curated datasets run successfully through `eval_extraction.py` with `mindt.toml`.

## Verification Plan

- Profile: `feature`
- Checks:
  - `workflow-integrity`
  - `runner-behavior`
  - `dataset-shape`
  - `docs-alignment`

## Open Questions

- None blocking. The main design constraint is to score relation extraction from extracted text signals rather than from downstream structured normalization.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
