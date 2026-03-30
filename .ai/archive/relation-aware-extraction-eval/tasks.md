# Tasks: relation-aware-extraction-eval

## Preconditions

- Proposal status is `approved`
- Spec impact is confirmed
- Verification profile is selected
- Open questions are either resolved or explicitly deferred

## Implementation

- [x] 1. Add relation-aware extraction evaluation support to `tests/eval/runners/eval_extraction.py` with backward compatibility
- [x] 2. Replace the fragmented legacy extraction datasets with one curated 100-case general dataset
- [x] 3. Add a comprehensive 100-case relationship-only extraction dataset
- [x] 4. Update docs and regression tests for the new extraction dataset topology

## Validation

- [x] Execute the selected verification profile
- [x] Create or update `verification-report.md`
- [x] Record manual verification performed
- [x] Record any skipped checks and why

## Closeout

- [x] Merge accepted spec updates into `.ai/specs/`
- [x] If `.ai/` changed, update the relevant `.human/` handbook documents as needed
- [ ] Move the completed change folder into `.ai/archive/`
