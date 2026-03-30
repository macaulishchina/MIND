# Tasks: postgres-pgvector-backend

## Preconditions

- Proposal status is `approved`
- Spec impact is confirmed
- Verification profile is selected
- Open questions are either resolved or explicitly deferred

## Implementation

- [x] 1. Add change-local backend wiring for Postgres vector and history stores
- [x] 2. Implement `pgvector` vector-store behavior with parity to the current vector-store contract
- [x] 3. Implement Postgres history persistence with parity to the current history API
- [x] 4. Update configuration, factories, and example/test config for the new backend
- [x] 5. Add or update verification coverage for storage and memory flows

## Validation

- [x] Execute the selected verification profile
- [x] Create or update `verification-report.md` from
      `.ai/verification/templates/verification-report.md`
- [x] Record any manual verification performed
- [x] Record any skipped checks and why

## Closeout

- [x] Merge accepted spec updates into `.ai/specs/` (not applicable: Spec impact `none`)
- [x] If `.ai/` changed, update the relevant `.human/` handbook documents as needed
- [ ] Move the completed change folder into `.ai/archive/`
