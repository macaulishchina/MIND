# Change Proposal: Extraction Prompt Generalization

## Metadata

- Change ID: `extraction-prompt-generalization`
- Type: `refactor`
- Status: `implementing`
- Spec impact: `none`
- Verification profile: `refactor`
- Owner: `GitHub Copilot`
- Related specs: `none`

## Summary

- Tighten the extraction prompt so it preserves fact structure more faithfully without adding dataset-specific rules.

## Why Now

- Current extraction reports show a small number of recurring weaknesses around subject ownership, hypothetical filtering, and compression of timeline/state-change facts.
- These can be improved at the prompt layer without introducing custom post-processing logic.

## In Scope

- Update fact extraction prompt instructions.
- Keep the change general-purpose and model-agnostic.
- Re-run focused extraction evaluation for evidence.

## Out Of Scope

- Dataset-specific parsing rules.
- Evaluator changes.
- New extraction pipeline logic.

## Proposed Changes

- Strengthen the prompt around atomic facts, user-subject filtering, preservation of original names/terms, and handling of past/current/committed-future facts.

## Reality Check

- Prompt-only changes cannot solve all evaluator mismatch issues.
- Over-constraining the prompt risks lower recall or stiffer wording; the change should remain minimal and broadly applicable.

## Acceptance Signals

- No regression on easy/medium/tricky extraction behavior.
- Blackbox failure profile improves or at least shifts toward cleaner factual boundaries.

## Verification Plan

- Use the `refactor` profile.
- Run extraction eval on the blackbox dataset and, if feasible, one easier dataset for sanity.
- Review the changed prompt manually for overfitting risk.

## Open Questions

- None blocking.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
