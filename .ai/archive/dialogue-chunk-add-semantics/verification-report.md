# Verification Report: dialogue-chunk-add-semantics

## Metadata

- Change ID: `dialogue-chunk-add-semantics`
- Verification profile: `full`
- Status: `complete`
- Prepared by: `Codex`

## Checks Run

### `workflow-integrity`

- Result: `pass`
- Evidence:
  - Created proposal, tasks, change-local spec deltas, and verification report under `.ai/changes/dialogue-chunk-add-semantics/` before archive.
  - Merged approved spec updates into `.ai/specs/owner-centered-memory/spec.md` and `.ai/specs/owner-centered-add-eval/spec.md`.
- Notes:
  - The change updates capability specs, not `.ai/` workflow guidance; no `.human/` handbook sync was required.

### `change-completeness`

- Result: `pass`
- Evidence:
  - `mind/memory.py` now treats one `add()` call as one submitted dialogue chunk and projects only current statements from that chunk.
  - `tests/eval/runners/eval_owner_centered_add.py` now flattens case turns and calls `Memory.add()` once per case.
  - `tests/eval/README.md`, eval cases, and regression tests were rewritten to match the new metric surface.
- Notes:
  - Cross-submission update/version behavior remains covered in runtime tests, not owner-centered add eval.

## Additional Checks

### `automated-pytest`

- Result: `pass`
- Evidence:
  - `.venv/bin/python -m pytest -q tests/test_memory.py tests/test_eval_owner_centered_add.py`
  - Result: `23 passed in 69.28s`
- Notes:
  - Coverage includes the new chunk-final single-value behavior and the single-add-per-case runner contract.

### `automated-cli`

- Result: `pass`
- Evidence:
  - `.venv/bin/python tests/eval/runners/eval_owner_centered_add.py --toml mindt.toml --provider fake --model fake-memory-test --case tests/eval/cases/owner-add-005.json --pretty`
  - Summary reported all configured metric targets passed for `owner-add-005`.
- Notes:
  - A separate exploratory run against a real provider was not used as acceptance evidence because model variance is outside this deterministic verification profile.

### `manual-doc-review`

- Result: `pass`
- Evidence:
  - Reviewed `tests/eval/README.md` and `.ai/specs/*` for stale per-turn `Memory.add()` semantics.
  - Verified the owner-centered add docs no longer describe update/version metrics as part of the main eval surface.
- Notes:
  - Historical references remain in `.ai/archive/` as traceability records and were intentionally not rewritten.

## Residual Risk

- Real external LLMs may still emit STL that does not fully normalize a complex multi-turn chunk into the desired final owner-memory shape in one pass.
- The chunk-level projection logic now prevents batch-internal owner-memory version chains, but broader semantic quality for real-model correction-heavy cases still depends on STL extraction quality.

## Summary

- The selected `full` profile is satisfied.
- The repo now has one coherent owner-centered add contract: one case, one flattened dialogue chunk, one `Memory.add()` call.
