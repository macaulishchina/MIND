# Execution Plan

## Goal

- Add a challenge-first, reality-check gate to the workflow so AI must surface
  conflicts, infeasibility, and better alternatives before implementation.

## Why Now

- The current workflow is strong on proposal, approval, tasks, and verification,
  but it still risks turning immature directions into half-finished execution.
- We want the system to value truth and better direction over obedient but low-value implementation.

## Constraints

- Keep the existing `.ai/` and `.human/` structure intact.
- Add the new behavior as a workflow rule, not as a vague style preference.
- Preserve the current proposal-approval gate while making it more critical.

## Non-Goals

- Changing the archive/spec/verification model.
- Adding automated feasibility tooling.
- Making the workflow adversarial for the sake of it.

## Affected Areas

- `AGENTS.md`
- `.ai/README.md`
- `.ai/project.md`
- `.ai/changes/README.md`
- `.ai/templates/proposal.md`
- `.ai/verification/checks/workflow-integrity.md`
- `.ai/verification/checks/change-completeness.md`
- `.human/context.md`
- `.human/workflow.md`
- `.human/quick-start.md`
- `.human/templates.md`

## Risks

- If the new rule is too weak, AI will still execute bad directions too eagerly.
- If the new rule is too vague, humans will not know when a challenge is expected.

## Steps

1. Add a formal reality-check requirement to the workflow entrypoints.
2. Update the proposal template so each non-small change records feasibility,
   conflicts, and better alternatives when relevant.
3. Update verification checks so proposal quality includes reality-check coverage.
4. Update the Chinese developer handbook so humans understand the same rule.

## Verification

- Spot-check all workflow entrypoints for challenge-first wording.
- Confirm the proposal template includes a dedicated reality-check section.
- Confirm the handbook explains that AI should challenge bad directions instead
  of blindly implementing them.

## Progress Log

- `done` Re-read the current workflow entrypoints, proposal template, and handbook.
- `done` Added the challenge-first rule to `.ai/` and `.human/`.
- `done` Updated the proposal template and workflow checks with a reality-check requirement.
- `done` Verified that the workflow no longer implies blind execution.

## Decisions

- The proposal gate now includes a reality check before approval.
- Challenge is treated as a responsibility, not as defiance for its own sake.

## Open Questions

- Whether future tooling should track unresolved feasibility objections explicitly.
