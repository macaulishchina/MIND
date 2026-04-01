# Verification Report: stl-v2-grammar

## Metadata

- Change ID: `stl-v2-grammar`
- Verification profile: `full`
- Status: `complete`
- Prepared by: `agent`

## Checks Run

### `workflow-integrity`

- Result: `pass`
- Evidence: proposal.md, spec.md, tasks.md all present; all tasks completed
- Notes: spec written before implementation; proposal contains reality check

### `change-completeness`

- Result: `pass`
- Evidence: All 15 tasks (T1–T15) completed
- Notes:
  - Models, parser, vocab, prompt, store fully rewritten to v2
  - All 18 eval JSON cases updated
  - Eval runners updated (evidence metrics removed)
  - Fake LLM, focus.py, test files all migrated
  - Evidence DDL, VocabCategory enum, .v1bak files removed

### `test-suite`

- Result: `pass`
- Evidence: `pytest tests/ -x --tb=short -q` → **190 passed** in 58.15s
- Notes: Zero failures, zero warnings on v2 codebase

### `grammar-completeness`

- Result: `pass`
- Evidence: All 15 v1 examples (§11.1–§11.15) re-expressed in v2 in spec.md
- Notes: EBNF is unambiguous; every valid input has exactly one parse

### `spec-consistency`

- Result: `pass`
- Evidence: Implementation matches spec on all points:
  - 3+1 line types (REF, STMT, NOTE, COMMENT)
  - 4 atomic arg types only
  - 3-level parse cascade (strict/fuzzy/fallback)
  - 85 seed predicates in 6 domains
  - `:suggested_word` mechanism
  - `@self` implicit, no scope

## Residual Risk

- `Doc/core/语义翻译层.md` is being updated as part of cleanup (was v1)
- The `stl-evidence` spec in `.ai/specs/` is superseded by v2 (evidence removed)

## Summary

- The `full` verification profile is satisfied.
- 190 tests passing. Grammar spec complete. All code migrated.
