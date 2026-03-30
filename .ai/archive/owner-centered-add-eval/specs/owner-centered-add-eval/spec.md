# Spec: owner-centered-add-eval

## ADDED Requirements

### Requirement: Owner-Centered Add Evaluation Runner

The repository SHALL provide a dedicated evaluation runner for the owner-centered `Memory.add()` pipeline.

#### Scenario: Runner Evaluates Multi-Turn Owner-Centered Cases

- WHEN the owner-centered add evaluation runner executes a dataset case
- THEN it applies the case turns in order through `Memory.add()` and evaluates the resulting memory state against the case expectations

### Requirement: Owner-Centered Add Dataset Shape

The repository SHALL define a dataset format that can express owner context, ordered turns, and expected final memory state.

#### Scenario: Dataset Encodes Owner And Final Active Memories

- WHEN a dataset case is authored for owner-centered add evaluation
- THEN it can express the owner identity used for the case, the ordered add turns, and the expected final active memories including canonical text and subject references

### Requirement: Owner-Centered Add Report Metrics

The runner SHALL report structured metrics for the owner-centered add pipeline beyond extraction-only metrics.

#### Scenario: Report Includes Structured Outcome Metrics

- WHEN the owner-centered add evaluation runner finishes
- THEN its report includes metrics covering canonical text accuracy, subject reference accuracy, active-memory count accuracy, update behavior accuracy, and case pass rate
