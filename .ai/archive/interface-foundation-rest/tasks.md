# Tasks: interface-foundation-rest

## Preconditions

- Proposal status is `approved`
- Spec impact is confirmed
- Verification profile is selected
- Open questions are either resolved or explicitly deferred

## Implementation

- [x] 1. Add the change-local spec delta and configuration surface for REST
- [x] 2. Implement the application layer DTOs, service, and error mapping
- [x] 3. Implement the FastAPI adapter and reserve MCP/CLI interface slots
- [x] 4. Add deterministic application and REST tests
- [x] 5. Update README and local API development docs

## Validation

- [x] Run focused pytest coverage for application and REST behavior
- [x] Run `.venv/bin/python -m pytest tests/`
- [x] Create `verification-report.md`
- [x] Record any manual review notes or skipped checks

## Closeout

- [x] Merge accepted spec updates into `.ai/specs/`
- [x] If `.ai/` changed, update the relevant `.human/` handbook documents as needed
- [x] Move the completed change folder into `.ai/archive/`
