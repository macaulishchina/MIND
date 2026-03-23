# Execution Plan

## Goal

- Add a generic verification layer to `.ai/` so the spec workflow has a
  reusable validation model without depending on any concrete script.

## Why Now

- The current workflow explains when to propose, approve, implement, and
  archive, but verification is still described too loosely.
- The repository has no substantive code yet, so the right move is to define
  the verification model first and defer any concrete runner scripts.

## Constraints

- Keep verification script-free for now.
- Make verification fit naturally into the existing `.ai` workflow.
- Prefer a reusable model that still works when the repository later gains real
  code and toolchain commands.

## Non-Goals

- Implementing `ai_health_check.py` or any other runner.
- Defining product-specific technical checks that the repo has not earned yet.
- Reverting the existing `project/specs/changes/archive` workflow layout.

## Affected Areas

- `.ai/README.md`
- `.ai/project.md`
- `.ai/templates/proposal.md`
- `.ai/templates/tasks.md`
- `.ai/verification/`

## Risks

- If verification stays too abstract, it will not help real change execution.
- If profiles and checks overlap too much, future agents will not know which to use.

## Steps

1. Add a dedicated `.ai/verification/` subsystem with policy, profiles, checks,
   and a reporting template.
2. Update the workflow entrypoints so non-small changes select and execute a
   verification profile.
3. Update proposal and task templates so verification is planned and recorded
   as part of each change.
4. Verify the final structure and confirm there are no remaining references to
   the old script-first model.

## Verification

- Inspect the final `.ai/verification/` tree.
- Spot-check `README.md`, `project.md`, and change templates for verification
  workflow integration.
- Search for stale references to `scripts/ai_health_check.py` or other
  script-first assumptions and keep only an explicit historical note if needed.

## Progress Log

- `done` Re-read the current `.ai` workflow entrypoints and task template.
- `done` Added the verification subsystem with policy, profiles, checks, and a report template.
- `done` Wired verification into the main workflow entrypoints and change templates.
- `done` Verified that the resulting model is self-consistent and script-agnostic.

## Decisions

- Verification will be modeled as policy + profiles + checks + report template.
- Profiles will be reusable workflow levels, not bound to any language toolchain.
- Manual verification remains valid when no automated runner exists.

## Open Questions

- Which additional verification checks should exist once the repository gains a
  real implementation stack.
