# Active Changes

Each folder under `.ai/changes/` represents one proposed or active change.

## Naming

- Use a short kebab-case change id such as `add-profile-filters`
- Keep one business objective per change folder

## Required Files

- `proposal.md`
- `tasks.md` before implementation starts
- `verification-report.md` before archive
  Copy from `.ai/verification/templates/verification-report.md`.

## Conditional Files

- `design.md` when technical decisions need durable explanation
- `specs/<capability>/spec.md` when the change affects behavior, contracts, or
  acceptance criteria

## Expected Lifecycle

1. Draft `proposal.md`
2. Add spec delta if needed
3. Clarify and review
4. Select a verification profile
5. Mark the proposal approved
6. Finalize `tasks.md`
7. Implement
8. Complete and record verification
9. Merge approved spec updates into `.ai/specs/`
10. Move the whole folder to `.ai/archive/`
