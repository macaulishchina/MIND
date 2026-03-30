# Verification Report: relation-aware-extraction-eval

## Metadata

- Change ID: `relation-aware-extraction-eval`
- Verification profile: `feature`
- Status: `complete`
- Prepared by: `Codex`

## Checks Run

### `workflow-integrity`

- Result: `pass`
- Evidence:
  - Created and used `.ai/changes/relation-aware-extraction-eval/` with proposal, tasks, spec delta, and this verification report.
  - Merged accepted spec updates into `.ai/specs/memory-add-extraction/spec.md`.
- Notes:
  - `.human/verification.md` and `.human/workflow.md` were reviewed; no handbook update was needed because developer rules did not change, only evaluation content and maintained datasets changed.

### `runner-behavior`

- Result: `pass`
- Evidence:
  - `pytest -q tests/test_eval_extraction.py`
  - `python tests/eval/runners/eval_extraction.py --toml mindt.toml --fail-on-targets`
  - `python tests/eval/runners/eval_extraction.py --toml mindt.toml --dataset tests/eval/datasets/extraction_relationship_cases.json --fail-on-targets`
- Notes:
  - Default discovery now evaluates exactly the curated general dataset plus the relation-focused dataset.
  - Relation-aware metrics are emitted only when a dataset includes relation annotations.

### `dataset-shape`

- Result: `pass`
- Evidence:
  - `tests/eval/datasets/extraction_curated_cases.json` contains 100 cases and no relation annotations.
  - `tests/eval/datasets/extraction_relationship_cases.json` contains 100 cases and relation annotations on every case.
  - Obsolete files removed:
    - `tests/eval/datasets/extraction_easy_cases.json`
    - `tests/eval/datasets/extraction_medium_cases.json`
    - `tests/eval/datasets/extraction_hard_cases.json`
    - `tests/eval/datasets/extraction_tricky_cases.json`
    - `tests/eval/datasets/blackbox/extraction_blackbox_cases.json`
- Notes:
  - The curated general dataset preserves provenance via `legacy_source` so selected cases can still be traced back to their previous source files.

### `docs-alignment`

- Result: `pass`
- Evidence:
  - Updated `tests/eval/README.md`
  - Updated `Doc/evolution/memory.add/eval_framework.md`
  - Updated `.ai/specs/memory-add-extraction/spec.md`
- Notes:
  - Documentation now points to the curated general dataset and the relationship extraction dataset instead of the retired difficulty-layered / blackbox topology.

## Residual Risk

- The new relationship dataset is comprehensive, but it still scores relation signals from extracted free text rather than from downstream normalized relation objects. That is intentional for extraction-stage evaluation, but it means this runner is not a substitute for owner-centered end-to-end add evaluation.

## Summary

- Relation-aware extraction evaluation is implemented, legacy extraction datasets are consolidated into a single curated 100-case general regression set, and a second 100-case relationship-focused dataset now measures relation-bearing extraction behavior directly.
