# Tasks: remove-legacy-extraction-eval

## Preconditions

- Proposal status is `approved`
- Spec impact is confirmed
- Verification profile is selected
- Open questions are either resolved or explicitly deferred

## Implementation

- [x] 1. Remove the legacy extraction eval runner, its datasets, and its dedicated runner tests.
- [x] 2. Update user-facing and developer-facing docs so STL-native owner-centered eval is the only maintained eval path.
- [x] 3. Merge the approved living-spec update that removes extraction-eval maintenance requirements while keeping the helper contract.

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
