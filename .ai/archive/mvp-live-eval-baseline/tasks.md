# Tasks: mvp-live-eval-baseline

## Preconditions

- Proposal status is `approved`
- Spec impact is confirmed
- Verification profile is selected
- Open questions are either resolved or explicitly deferred

## Implementation

- [x] 1. Add the change-local proposal artifacts and MVP live-baseline spec delta
- [x] 2. Run the real `owner_add` baseline eval with `mind.toml` and save the tracked report
- [x] 3. Add a concise baseline summary and update MVP-facing evaluation docs
- [x] 4. Merge the approved live-baseline expectation into the maintained living spec

## Validation

- [x] Run `.venv/bin/python -m pytest tests/`
- [x] Run the live owner-add eval command and record its evidence
- [x] Create `verification-report.md` from the verification template
- [x] Record manual review notes, residual risk, and `.human/` sync impact

## Closeout

- [x] Merge accepted spec updates into `.ai/specs/`
- [x] If `.ai/` changed, update the relevant `.human/` handbook documents as needed
- [x] Move the completed change folder into `.ai/archive/`
