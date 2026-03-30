# Verification Report: owner-centered-add-eval

## Metadata

- Change ID: `owner-centered-add-eval`
- Verification profile: `feature`
- Status: `complete`
- Prepared by: `Codex`

## Checks Run

### `workflow-integrity`

- Result: `pass`
- Evidence:
  - `.ai/archive/owner-centered-add-eval/proposal.md` created and approved before implementation
  - `.ai/archive/owner-centered-add-eval/tasks.md` completed
  - Change-local spec delta recorded at `.ai/archive/owner-centered-add-eval/specs/owner-centered-add-eval/spec.md`
- Notes:
  - `.ai/` workflow guidance did not change, so `.human/` updates were not required for this feature change.

### `runner-behavior`

- Result: `pass`
- Evidence:
  - `pytest -q`
    - Result: `49 passed in 3.01s`
  - `python tests/eval/runners/eval_owner_centered_add.py --toml mindt.toml --output tests/eval/reports/owner_centered_add_cases_report.json --fail-on-targets`
    - Result: exit `0`
    - Summary metrics:
      - `canonical_text_accuracy = 1.000`
      - `subject_ref_accuracy = 1.000`
      - `count_accuracy = 1.000`
      - `update_accuracy = 1.000`
      - `owner_accuracy = 1.000`
- Notes:
  - The runner reuses configured LLM and embedding clients, but isolates persistence with ephemeral in-memory Qdrant and temporary SQLite history storage.

### `dataset-shape`

- Result: `pass`
- Evidence:
  - Dataset added at `tests/eval/datasets/owner_centered_add_cases.json`
  - Coverage includes:
    - known owner self facts
    - anonymous owner reuse across turns
    - named third-party subject refs
    - unnamed third-party placeholder refs
    - single-value update and versioning behavior
  - Targeted tests:
    - `tests/test_eval_owner_centered_add.py::test_owner_centered_dataset_loads`
    - `tests/test_eval_owner_centered_add.py::test_case_owner_lookup_supports_known_and_anonymous_owners`
- Notes:
  - The dataset format records owner identity, ordered turns, expected active memories, and optional deleted/versioned expectations.

### `docs-alignment`

- Result: `pass`
- Evidence:
  - `Doc/evolution/memory.add/eval_framework.md` updated to distinguish extraction-only eval from owner-centered add eval
  - Added command examples and metrics description for `tests/eval/runners/eval_owner_centered_add.py`
  - `tests/eval/runners/eval_extraction.py` updated to honor `[llm.extraction]` stage config so extraction eval remains aligned with staged runtime behavior
- Notes:
  - Extraction eval remains intentionally scoped to `_extract_facts()`; the new runner covers end-to-end owner-centered add behavior.

## Residual Risk

- The owner-centered add runner validates deterministic baseline behavior cleanly with `mindt.toml` and fake backends. Real external LLMs may still introduce noise in normalization quality that this baseline does not eliminate.
- The runner inspects deleted memories via vector-store listing because the public API exposes only active memories; if storage internals change, the runner may need light adaptation.

## Summary

- The repository now has a dedicated owner-centered add evaluation path with dataset coverage, JSON reporting, human-readable summaries, tests, and docs.
- Verification passed for the selected `feature` profile.
