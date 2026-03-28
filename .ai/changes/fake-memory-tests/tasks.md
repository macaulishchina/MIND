# Tasks: fake-memory-tests

Finalize this file only after the proposal is approved.

## Preconditions

- Proposal status is `approved`
- Spec impact is confirmed
- Verification profile is selected
- Open questions are either resolved or explicitly deferred

## Implementation

- [ ] 1. Add fake LLM backend
- [ ] 2. Add fake embedding backend
- [ ] 3. Register fake protocols in factories
- [ ] 4. Switch memory tests to fake config and remove API-key gating
- [ ] 5. Run focused verification

## Validation

- [ ] Execute the selected verification profile
- [ ] Create or update `verification-report.md` from
      `.ai/verification/templates/verification-report.md`
- [ ] Record any manual verification performed
- [ ] Record any skipped checks and why

## Closeout

- [ ] Merge accepted spec updates into `.ai/specs/`
- [ ] If `.ai/` changed, update the relevant `.human/` handbook documents as needed
- [ ] Move the completed change folder into `.ai/archive/`
