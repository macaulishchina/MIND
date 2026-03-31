# Tasks: runtime-logging-alignment

## Preconditions

- Proposal status is `approved`
- Spec impact is confirmed
- Verification profile is selected
- Open questions are either resolved or explicitly deferred

## Implementation

- [x] 1. Extract or add a reusable runtime logging bootstrap that can be called outside `Memory`
- [x] 2. Update current callers to use the shared bootstrap and fix stale ops-switch behavior on reconfiguration
- [x] 3. Add or update focused tests for direct LLM logging and verbose detail behavior
- [x] 4. Update eval docs/examples to reflect the plain latency runner logging behavior

## Validation

- [x] Execute the selected verification profile
- [x] Create or update `verification-report.md` from `.ai/verification/templates/verification-report.md`
- [x] Record any manual verification performed
- [x] Record any skipped checks and why

## Closeout

- [x] Merge accepted spec updates into `.ai/specs/`
- [x] If `.ai/` changed, update the relevant `.human/` handbook documents as needed
- [x] Move the completed change folder into `.ai/archive/`
