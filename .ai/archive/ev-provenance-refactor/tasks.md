# Tasks: ev-provenance-refactor

## Preconditions

- Proposal status is `approved`
- Spec impact is confirmed: update required
- Verification profile: `feature`
- Open questions: none

## Implementation

- [x] 1. Remove `src` from `ParsedEvidence` model (`mind/stl/models.py`)
- [x] 2. Remove `src` parsing from parser (`mind/stl/parser.py`)
- [x] 3. Remove `src` from prompt (`mind/stl/prompt.py`)
- [x] 4. Update store: evidence DDL + `insert_evidence` + `store_program` (`mind/stl/store.py`)
- [x] 5. Remove `src` generation from fake LLM (`mind/llms/fake.py`)
- [x] 6. Update tests (parser, store, phase2, phase3, fake_llm)
- [x] 7. Update eval datasets (remove `src` from `expected_evidence`)
- [x] 8. Update eval runner (`eval_owner_centered_add.py`)
- [x] 9. Update design doc (`Doc/core/语义翻译层.md`)

## Validation

- [x] Execute the selected verification profile
- [x] Create or update `verification-report.md`
- [x] Record any manual verification performed

## Closeout

- [x] Merge accepted spec updates into `.ai/specs/`
- [x] Move the completed change folder into `.ai/archive/`
