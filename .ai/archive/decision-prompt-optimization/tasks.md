# Tasks: decision-prompt-optimization

## Preconditions

- Proposal status is `approved`
- Spec impact is confirmed
- Verification profile is selected
- Open questions are either resolved or explicitly deferred

## Implementation

- [x] 1. Define the maintained decision-stage case schema and seed dataset under
      `tests/eval/decision_opt/`
- [x] 2. Implement shared decision prompt evaluation utilities plus a direct
      A/B runner for control vs candidate prompt text
- [x] 3. Implement an offline self-optimization script that can propose bounded
      prompt deltas, evaluate them, and gate promotion without runtime prompt
      mutation
- [x] 4. Use the new workflow to strengthen `UPDATE_DECISION_SYSTEM_PROMPT` and
      record the first baseline/candidate artifacts
- [x] 5. Add or update pytest coverage and repo docs for the new decision-stage
      evaluation workflow

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
