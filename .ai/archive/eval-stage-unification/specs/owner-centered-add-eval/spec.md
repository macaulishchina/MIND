# Spec: owner-centered-add-eval

## MODIFIED Requirements

### Requirement: Owner-Centered Add Evaluation Runner

The repository SHALL provide owner-centered add evaluation through the shared eval stage runner for the `Memory.add()` pipeline, evaluating STL-backed persisted state rather than relying only on extraction-stage free-text output.

#### Scenario: Owner-Add Stage Evaluates One Case

- WHEN the unified eval runner executes a case with `--stage owner_add`
- THEN it flattens the case `turns` into one ordered message list
- AND it submits that case through a single `Memory.add()` call
- AND it evaluates the resulting current STL-backed memory state against the case's `stages.owner_add` expectations

### Requirement: Owner-Centered Add Dataset Shape

The repository SHALL define owner-centered add expectations as one stage section within the shared eval case format.

#### Scenario: Case Stores Owner-Add Expectations In A Stage Block

- WHEN a case supports owner-centered add evaluation
- THEN it stores owner-centered add assertions under `stages.owner_add`
- AND those assertions can express projected active-memory expectations plus any owner-add-specific final-state checks
