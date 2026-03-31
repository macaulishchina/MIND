# Verification Report: remove-legacy-extraction-eval

## Metadata

- Change ID: `remove-legacy-extraction-eval`
- Verification profile: `refactor`
- Status: `complete`
- Prepared by: `Codex`

## Checks Run

### `workflow-integrity`

- Result: `pass`
- Evidence:
  - Proposal approved in `.ai/archive/remove-legacy-extraction-eval/proposal.md`
  - Change-local spec delta recorded in `.ai/archive/remove-legacy-extraction-eval/specs/memory-add-extraction/spec.md`
  - Tasks and this verification report were created before archive
- Notes:
  - The change updates living specs and repo docs, so spec and doc consistency was reviewed as part of closeout

### `change-completeness`

- Result: `pass`
- Evidence:
  - Removed legacy runner: `tests/eval/runners/eval_extraction.py`
  - Removed legacy datasets:
    - `tests/eval/datasets/extraction_curated_cases.json`
    - `tests/eval/datasets/extraction_relationship_cases.json`
  - Removed legacy runner tests: `tests/test_eval_extraction.py`
  - Updated docs:
    - `tests/eval/README.md`
    - `README.md`
  - Removed obsolete design doc: `Doc/evolution/memory.add/eval_framework.md`
  - Updated living spec: `.ai/specs/memory-add-extraction/spec.md`
- Notes:
  - Remaining extraction helper coverage in `tests/test_extraction.py` was intentionally kept

## Additional Checks

### `behavior-parity`

- Result: `pass`
- Evidence:
  - `pytest -q tests`
    - `180 passed in 18.61s`
  - `python tests/eval/runners/eval_owner_centered_add.py --toml mindt.toml --pretty`
    - all three STL-native datasets passed all metric targets
- Notes:
  - The maintained STL-native evaluation path remains healthy after removing the legacy extraction eval surface

### `manual-review`

- Result: `pass`
- Evidence:
  - Verified `mind/memory.py` runtime add path uses `_extract_stl()` and no longer depends on `_extract_facts()` for business-path acceptance
  - Verified no remaining tracked docs or test entrypoints reference `eval_extraction.py` or the deleted extraction datasets
  - Reviewed `.human/workflow.md` and `.human/verification.md` for handbook impact
- Notes:
  - No `.human/` update was required because developer workflow guidance did not change

## Residual Risk

- `_extract_facts()` still exists as a legacy helper and is only protected by low-level unit tests now, not by dataset-driven eval
- Any future decision to remove `_extract_facts()` entirely should separately audit notebook and ad hoc helper usage such as `Jupyter/JupyterBase.py`

## Summary

- The selected `refactor` profile is satisfied
- No verification gaps are being accepted for this archived change
