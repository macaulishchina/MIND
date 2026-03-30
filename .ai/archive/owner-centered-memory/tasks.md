# Tasks: owner-centered-memory

## Preconditions

- Proposal status is `approved`
- Spec impact is confirmed
- Verification profile is selected
- Open questions are either resolved or explicitly deferred

## Implementation

- [x] 1. Add change-local spec delta for owner-centered memory behavior
- [x] 2. Implement owner resolution, owner-local subject references, and structured fact envelopes
- [x] 3. Extend storage and vector payloads with owner/subject/fact metadata
- [x] 4. Add stage-specific LLM configuration and update prompts/fake LLM behavior
- [x] 5. Update tests, notebook helper compatibility, and any affected docs

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
