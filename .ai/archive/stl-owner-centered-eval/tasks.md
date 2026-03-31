# Tasks: stl-owner-centered-eval

## Preconditions

- Proposal status is `approved`
- Spec impact is confirmed
- Verification profile is selected
- Open questions are either resolved or explicitly deferred

## Implementation

- [x] 1. Add STL-native fake/test support needed to run `Memory.add()` deterministically in evaluation.
- [x] 2. Implement `tests/eval/runners/eval_owner_centered_add.py` around the real `Memory.add()` pipeline.
- [x] 3. Add STL-backed dataset loading and case evaluation for owner identity, active memories, refs, statements, evidence, and update behavior.
- [x] 4. Restore a minimal owner-centered dataset set and update or replace the skipped owner-centered eval tests.
- [x] 5. Update evaluation docs to describe the STL-native runner and how it relates to legacy extraction eval.

## Validation

- [x] Execute the selected verification profile
- [x] Create or update `verification-report.md` from
      `.ai/verification/templates/verification-report.md`
- [x] Record any manual verification performed
- [x] Record any skipped checks and why

## Closeout

- [x] Merge accepted spec updates into `.ai/specs/`
- [x] If `.ai/` changed, update the relevant `.human/` handbook documents as needed
- [x] Move the completed change folder into `.ai/archive/`
