# Tasks: add-phase-optimization

## Preconditions

- Proposal status is `approved` or `implementing`
- Spec impact is confirmed
- Verification profile is selected

## Implementation

- [x] 1. Add extraction-stage prompt restructuring with clearer rules and few-shot guidance
- [x] 2. Add extraction output normalization before retrieval and decision
- [x] 3. Add extraction-specific temperature override support in config and LLM interfaces
- [x] 4. Add focused regression tests for extraction normalization and override behavior
- [x] 5. Update extraction-stage docs to reflect the implemented behavior
- [x] 6. Add extraction evaluation dataset and runnable benchmark script
- [x] 7. Split extraction evaluation into multiple focused datasets with dataset-derived report names
- [x] 8. Add richer diagnostic metrics and human-readable summaries to the extraction evaluator

## Validation

- [x] Run focused pytest coverage for extraction changes and existing memory pipeline tests
- [x] Create or update `verification-report.md`
- [x] Record manual verification performed
- [x] Record any skipped checks and why

## Closeout

- [ ] Merge accepted spec updates into `.ai/specs/`
- [ ] If `.ai/` changed, update the relevant `.human/` handbook documents as needed
- [ ] Move the completed change folder into `.ai/archive/`