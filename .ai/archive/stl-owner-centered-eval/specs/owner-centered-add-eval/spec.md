# Spec: owner-centered-add-eval

## MODIFIED Requirements

### Requirement: Owner-Centered Add Evaluation Runner

The repository SHALL provide a dedicated evaluation runner for the owner-centered `Memory.add()` pipeline that evaluates STL-backed persisted state rather than relying only on extraction-stage free-text output.

#### Scenario: Runner Evaluates Multi-Turn STL-Backed Cases

- WHEN the owner-centered add evaluation runner executes a dataset case
- THEN it applies the case turns in order through `Memory.add()`
- AND it evaluates the resulting current STL-backed memory state against the case expectations

### Requirement: Owner-Centered Add Dataset Shape

The repository SHALL define a dataset format that can express owner context, ordered turns, and expected final STL-backed memory state for the owner-centered `Memory.add()` pipeline.

#### Scenario: Dataset Encodes Owner, Turns, And STL Expectations

- WHEN a dataset case is authored for owner-centered add evaluation
- THEN it can express the owner identity used for the case
- AND it can express the ordered add turns for that owner
- AND it can express expected current refs, statements, and evidence coverage
- AND it can optionally express projected-memory assertions including canonical text, subject references, and update behavior

### Requirement: Owner-Centered Add Report Metrics

The runner SHALL report structured metrics for the owner-centered add pipeline that reflect STL-backed outcomes rather than extraction-only free-text metrics.

#### Scenario: Report Includes STL And Projected Memory Metrics

- WHEN the owner-centered add evaluation runner finishes
- THEN its report includes metrics covering STL current-statement accuracy or coverage, reference accuracy, evidence coverage, projected active-memory accuracy, update behavior accuracy, and case pass rate

## ADDED Requirements

### Requirement: Legacy Extraction Corpora Can Be Reused For STL Evaluation

The repository SHALL support reusing high-value legacy extraction evaluation corpora as source inputs for STL-native owner-centered evaluation, while allowing their assertions to be rewritten around STL-backed outcomes.

#### Scenario: Migrated Extraction Cases Keep Inputs But Rewrite Assertions

- WHEN a legacy extraction case is adopted into owner-centered STL evaluation
- THEN its conversation input and coverage metadata may be retained
- AND its acceptance criteria are expressed in terms of STL-backed state rather than free-text fact matching
