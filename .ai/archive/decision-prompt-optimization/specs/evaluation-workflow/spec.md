# Spec: evaluation-workflow

## ADDED Requirements

### Requirement: Dedicated Decision Prompt Evaluation Workflow

The repository SHALL maintain a dedicated evaluation workflow for
`UPDATE_DECISION_SYSTEM_PROMPT` separate from coarse end-to-end owner-add
evaluation.

#### Scenario: Developer Evaluates Decision Prompt Directly

- WHEN a developer wants to assess or optimize the decision-stage prompt
- THEN they can run a maintained decision-focused evaluation workflow against a
  structured decision dataset
- AND the workflow reports decision-specific metrics such as action accuracy,
  acceptable-action accuracy, temp-id correctness, and text-constraint quality

### Requirement: Prompt Optimization Uses Offline Candidate Gating

The repository SHALL treat decision prompt self-optimization as an offline,
gated workflow rather than a runtime self-modifying behavior.

#### Scenario: Candidate Prompt Is Proposed

- WHEN a candidate decision prompt is generated for optimization
- THEN it is evaluated against the maintained dataset and promotion gates before
  any runtime default is changed
- AND promotion requires explicit review rather than automatic in-place prompt
  mutation
