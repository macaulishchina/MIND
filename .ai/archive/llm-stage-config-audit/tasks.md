# Tasks: llm-stage-config-audit

## Preconditions

- Proposal status is `approved`
- Spec impact is confirmed
- Verification profile is selected
- Open questions are either resolved or explicitly deferred

## Implementation

- [x] 1. Remove legacy extraction/normalization helper code, prompt branches, and unused tests/helpers
- [x] 2. Narrow stage-config parsing and runtime semantics to active STL-native stages
- [x] 3. Update default TOML files and docs to reflect the cleaned configuration surface
- [x] 4. Update living specs and change artifacts for legacy pipeline removal

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
