# Verification Report: ev-provenance-refactor

## Metadata

- Change ID: `ev-provenance-refactor`
- Verification profile: `feature`
- Status: `complete`
- Prepared by: `agent`

## Checks Run

### `spec-consistency`

- Result: `pass`
- Evidence:
  - Proposal describes removing `src` from `ev()` syntax and adding `batch_id` to evidence table for system-side provenance.
  - Spec delta (`specs/stl-evidence/spec.md`) matches: MODIFIED ev-syntax (removed src), MODIFIED evidence-table-schema (added batch_id), REMOVED ev-src-parameter, ADDED evidence-batch-provenance.
  - Tasks cover all files listed in the proposal scope.
  - Source-of-truth spec (`Doc/core/语义翻译层.md`) was updated only during implementation, not during drafting.
- Notes: Proposal and spec delta are fully aligned.

### `workflow-integrity`

- Result: `pass`
- Evidence:
  - `proposal.md` exists with status `approved` and all approval checkboxes checked.
  - Reality check recorded in proposal (feasibility confirmed, no conflicts).
  - `tasks.md` created after proposal approval.
  - Change folder contains: proposal.md, tasks.md, specs/stl-evidence/spec.md, verification-report.md.
- Notes: All workflow steps followed in order.

### `change-completeness`

- Result: `pass`
- Evidence:
  - Proposal clearly states scope (remove `src`, add `batch_id`) and outcome.
  - Tasks reflect all 9 implemented work items, all checked off.
  - No open questions remain.
  - No `.human/` handbook sections affected (this change modifies internal STL mechanics, no developer-facing handbook exists for STL yet).
- Notes: Archive-ready.

### `manual-review`

- Result: `pass`
- Evidence:
  - All changed files reviewed end-to-end:
    - `mind/stl/prompt.py` — `src` removed from ev() syntax and rules
    - `mind/stl/models.py` — `src` field removed from `ParsedEvidence`
    - `mind/stl/parser.py` — `_RE_KV_SRC` regex removed, fuzzy typos cleaned, `ParsedEvidence` construction updated
    - `mind/stl/store.py` — DDL updated (both SQLite + Postgres), `insert_evidence` signatures updated, `store_program` passes `batch_id`
    - `mind/llms/fake.py` — `turn_index`/`src` generation removed from `prop()` and all callers
    - 5 test files updated (parser, store, phase2, phase3, fake_llm)
    - 2 eval dataset JSON files updated
    - 1 eval runner updated
    - Design doc (`Doc/core/语义翻译层.md`) fully updated: §7 Evidence section, five-forms line, EBNF, examples, DDL, mapping table, fuzzy parser rules
  - Full test suite: **185 passed, 0 failed** (`python -m pytest tests/ -v`)
- Notes: No behavioral regression detected.

## Residual Risk

- **Postgres DDL migration**: The Postgres evidence table DDL was updated in-code, but no migration script was created for existing databases. This is acceptable because the project is pre-production (no live Postgres instances with data).
- **`batch_id` foreign key enforcement**: The SQLite backend creates the `extraction_batches` table and the FK reference. If `store_program` is called without first creating an extraction batch, the FK will reject the insert. Current flow always creates a batch first, so this is safe.

## Summary

- The `feature` profile is fully satisfied.
- All 4 required checks pass.
- 185/185 tests pass with no regressions.
- No gap is being accepted.
