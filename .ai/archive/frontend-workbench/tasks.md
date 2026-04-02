# Tasks: frontend-workbench

## Preconditions

- Proposal status is `approved`
- Spec impact is confirmed
- Verification profile is selected
- Open questions are either resolved or explicitly deferred

## Implementation

- [x] 1. Add the change-local spec delta for the workbench surface
- [x] 2. Create the standalone React + Vite + TypeScript project under `frontend/`
- [x] 3. Implement the Playground and Memory Explorer flows on top of REST
- [x] 4. Add frontend tests and supporting tooling/config
- [x] 5. Update repo docs for running REST and frontend together

## Validation

- [x] Install frontend dependencies with the local Node toolchain
- [x] Run frontend tests
- [x] Run frontend build
- [x] Run `.venv/bin/python -m pytest tests/`
- [x] Create `verification-report.md`

## Closeout

- [x] Merge accepted spec updates into `.ai/specs/`
- [x] If `.ai/` changed, update the relevant `.human/` handbook documents as needed
- [x] Move the completed change folder into `.ai/archive/`
