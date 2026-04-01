# Tasks: dialogue-chunk-add-semantics

## Preconditions

- Proposal status is `approved`
- Spec impact is confirmed
- Verification profile is selected
- Open questions are either resolved or explicitly deferred

## Implementation

- [x] 1. Define the chunk-level runtime and eval semantics in change-local specs.
- [x] 2. Refactor `Memory.add()` projection so one submitted chunk yields only final current owner memories.
- [x] 3. Rewrite owner-centered add eval execution, dataset assertions, report metrics, and regression tests around single-submit cases.
- [x] 4. Update repo docs and living specs to remove stale per-turn eval semantics.

## Validation

- [x] Execute the selected verification profile.
- [x] Create or update `verification-report.md` from `.ai/verification/templates/verification-report.md`.
- [x] Record any manual verification performed.
- [x] Record any skipped checks and why.

## Closeout

- [x] Merge accepted spec updates into `.ai/specs/`.
- [x] If `.ai/` changed, update the relevant `.human/` handbook documents as needed.
- [x] Move the completed change folder into `.ai/archive/`.
