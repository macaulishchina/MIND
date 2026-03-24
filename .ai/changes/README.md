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
2. Challenge the requested direction against feasibility, conflicts, and better alternatives
3. Add spec delta if needed
4. Clarify and review
5. Select a verification profile
6. Mark the proposal approved
7. Finalize `tasks.md`
8. Implement
9. Complete and record verification
10. Merge approved spec updates into `.ai/specs/`
11. If `.ai/` workflow docs changed, update the relevant `.human/` handbook
12. Move the whole folder to `.ai/archive/`
