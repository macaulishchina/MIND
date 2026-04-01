# Tasks: eval-stage-unification

## Preconditions

- [x] Proposal status is `approved`
- [x] Spec impact is confirmed
- [x] Verification profile is selected
- [x] Open questions are either resolved or explicitly deferred

## Implementation

- [x] 1. Define the shared eval case schema and stage-oriented spec deltas.
- [x] 2. Implement the unified stage runner and shared dataset utilities.
- [x] 3. Rewrite existing eval cases and pytest coverage around the new stage layout.
- [x] 4. Update docs and remove stale eval entrypoints or references.

## Validation

- [x] Execute the selected verification profile.
- [x] Create or update `verification-report.md` from `.ai/verification/templates/verification-report.md`.
- [x] Record any manual verification performed.
- [x] Record any skipped checks and why.

## Closeout

- [x] Merge accepted spec updates into `.ai/specs/`.
- [x] If `.ai/` changed, update the relevant `.human/` handbook documents as needed.
- [x] Move the completed change folder into `.ai/archive/`.
