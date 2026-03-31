# Change Proposal: Remove Legacy Extraction Eval

## Metadata

- Change ID: `remove-legacy-extraction-eval`
- Type: `refactor`
- Status: `archived`
- Spec impact: `update required`
- Verification profile: `refactor`
- Owner: `Codex`
- Related specs: `memory-add-extraction`, `owner-centered-add-eval`

## Summary

- Remove the legacy extraction evaluation runner, its extraction-only datasets, and the test module that validates that legacy eval surface.
- Keep low-level `_extract_facts()` unit coverage for the helper itself, but stop treating extraction-only eval as a maintained business-facing acceptance path.

## Why Now

- The maintained `Memory.add()` runtime path is STL-native and no longer uses `_extract_facts()` as its main extraction stage.
- The legacy extraction eval currently measures a deprecated free-text fact surface that no longer represents the actual business pipeline.
- Keeping the runner and datasets around adds maintenance cost and points contributors toward the wrong acceptance target.

## In Scope

- Remove `tests/eval/runners/eval_extraction.py`
- Remove `tests/eval/datasets/extraction_*.json`
- Remove `tests/test_eval_extraction.py`
- Update docs and living specs that still advertise the legacy extraction eval as a maintained path

## Out Of Scope

- Removing `_extract_facts()` itself
- Removing low-level helper tests in `tests/test_extraction.py`
- Changing STL-native owner-centered evaluation semantics or datasets

## Proposed Changes

- Retire the extraction-only eval runner and its curated/relationship datasets from the maintained test surface.
- Update repo docs so the primary and only maintained eval entrypoint under `tests/eval/` is the STL-native owner-centered runner.
- Remove living-spec requirements that require the repository to maintain extraction-only eval datasets and relationship-signal metrics.

## Reality Check

- `_extract_facts()` still exists as a helper and still has direct unit coverage, so deleting every extraction-related test would be too aggressive.
- The business-facing issue is narrower: the extraction eval runner and its datasets no longer validate the active add pipeline, and they now compete with the STL-native eval as a misleading secondary acceptance target.
- Some historical docs still describe extraction eval as current practice. If we only delete code and datasets without updating docs/specs, the repo becomes internally inconsistent.

## Acceptance Signals

- No maintained test or README path points contributors to `eval_extraction.py`
- The extraction-only datasets are removed from `tests/eval/datasets/`
- STL-native owner-centered eval remains the only documented evaluation path
- Remaining extraction helper unit tests still pass

## Verification Plan

- Profile: `refactor`
- Checks requiring evidence:
  - `workflow-integrity`
  - `change-completeness`
  - `behavior-parity`
  - `manual-review`

## Open Questions

- None

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
