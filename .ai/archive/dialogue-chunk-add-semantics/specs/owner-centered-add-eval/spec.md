# Spec: owner-centered-add-eval

## MODIFIED Requirements

### Requirement: Owner-Centered Add Evaluation Runner

The repository SHALL provide a dedicated evaluation runner for the owner-centered `Memory.add()` pipeline that evaluates STL-backed persisted state rather than relying only on extraction-stage free-text output.

#### Scenario: Runner Evaluates Cases With One Chunk Submission

- WHEN the owner-centered add evaluation runner executes a dataset case
- THEN it flattens the case `turns` into one ordered message list
- AND it submits that case through a single `Memory.add()` call
- AND it evaluates the resulting current STL-backed memory state against the case expectations

### Requirement: Owner-Centered Add Dataset Shape

The repository SHALL define a dataset format that can express owner context, ordered dialogue turns, and expected final STL-backed memory state for the owner-centered `Memory.add()` pipeline.

#### Scenario: Dataset Encodes Owner, Turns, And Final-State Expectations

- WHEN a dataset case is authored for owner-centered add evaluation
- THEN it can express the owner identity used for the case
- AND it can express ordered dialogue turns as authoring structure
- AND it can express expected current refs, statements, and evidence coverage
- AND it can optionally express projected-memory assertions including canonical text and subject references

### Requirement: Owner-Centered Add Report Metrics

The runner SHALL report structured metrics for the owner-centered add pipeline that reflect STL-backed outcomes rather than extraction-only free-text metrics.

#### Scenario: Report Includes Final-State Metrics

- WHEN the owner-centered add evaluation runner finishes
- THEN its report includes metrics covering projected active-memory accuracy, owner accuracy, count accuracy, reference accuracy, statement accuracy, evidence accuracy, and case pass rate
- AND it does not treat cross-submission update/version/delete checks as part of the main owner-centered add metric surface
