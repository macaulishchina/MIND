# Tasks: test-llm-speed-hardening

## Preconditions

- Proposal status is `approved`
- Spec impact is confirmed
- Verification profile is selected
- Open questions are either resolved or explicitly deferred

## Implementation

- [x] 1. Harden test configuration so non-LLM-dependent tests use explicit fake-backed configs instead of relying on default TOML selection.
- [x] 2. Add concurrency support to `tests/eval/runners/eval_owner_centered_add.py` without changing report semantics or case isolation.
- [x] 3. Add or update regression tests covering the fake-config path and the concurrent owner-centered eval path.
- [x] 4. Update evaluation docs to describe the fake-first testing strategy and owner-centered eval concurrency.

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
