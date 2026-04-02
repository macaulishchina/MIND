# Tasks: chat-homepage-workbench

## Preconditions

- Proposal status is `approved`
- Spec impact is confirmed
- Verification profile is selected
- Open questions are either resolved or explicitly deferred

## Implementation

- [x] 1. Extend the typed config layer with curated chat model profiles and
      update example TOML files to advertise frontend-selectable chat choices
- [x] 2. Extend `mind/application/` with chat DTOs, profile discovery, and chat
      completion support while keeping STL/decision config internal
- [x] 3. Extend the REST adapter with chat-model discovery and chat-completion
      endpoints plus error handling for invalid profile ids
- [x] 4. Redesign the frontend into a chat-first workbench with model
      selection, local transcript persistence, and submit-only-new-memory logic
- [x] 5. Add or update Python and frontend tests for config resolution,
      application service, REST chat behavior, and the chat-first UI flow
- [x] 6. Update maintained docs and workflow context for the new chat-first
      workbench and adapter contract

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
