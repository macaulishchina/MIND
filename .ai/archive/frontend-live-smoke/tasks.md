# Tasks: frontend-live-smoke

## Preconditions

- Proposal status is `approved`
- Spec impact is confirmed
- Verification profile is selected
- Open questions are either resolved or explicitly deferred

## Implementation

- [x] 1. Add the change-local spec delta for the reproducible smoke path
- [x] 2. Add the safe local smoke config and any supporting launcher changes
- [x] 3. Update docs for running the frontend workbench against the smoke config
- [x] 4. Run and archive one successful live frontend + REST smoke

## Validation

- [x] Run targeted verification for launcher/config changes
- [x] Run `.venv/bin/python -m pytest tests/`
- [x] Record the manual live smoke evidence
- [x] Create `verification-report.md`

## Closeout

- [x] Merge accepted spec updates into `.ai/specs/`
- [x] If `.ai/` changed, update the relevant `.human/` handbook documents as needed
- [x] Move the completed change folder into `.ai/archive/`
