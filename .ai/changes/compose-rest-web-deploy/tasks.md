# Tasks: compose-rest-web-deploy

## Preconditions

- Proposal status is `approved`
- Spec impact is confirmed
- Verification profile is selected
- Open questions are either resolved or explicitly deferred

## Implementation

- [ ] 1. Add the change-local spec delta for compose-based REST/web deployment
- [ ] 2. Fix the pgvector startup failure on collection creation
- [ ] 3. Add backend/frontend container definitions and compose service graph
- [ ] 4. Update docs for compose startup and dependency behavior

## Validation

- [ ] Run targeted regression for pgvector and launcher/deployment changes
- [ ] Run frontend test/build and `.venv/bin/python -m pytest tests/`
- [ ] Validate `docker compose config`
- [ ] Create `verification-report.md`

## Closeout

- [ ] Merge accepted spec updates into `.ai/specs/`
- [ ] If `.ai/` changed, update the relevant `.human/` handbook documents as needed
- [ ] Move the completed change folder into `.ai/archive/`
