# Spec: evaluation-workflow

## ADDED Requirements

### Requirement: Shared Eval Case Format

The repository SHALL maintain a shared eval case format that separates reusable conversation input from stage-specific expectations.

#### Scenario: Common Inputs Are Reused Across Stages

- WHEN a case is authored under `tests/eval/cases/`
- THEN it stores reusable inputs such as `id`, `description`, `owner`, and `turns` once
- AND it stores stage-specific expectations under `stages.<stage-name>` blocks

### Requirement: Unified Eval Stage Runner

The repository SHALL provide one unified eval runner entrypoint for stage-based execution.

#### Scenario: Stage Selection Uses One CLI Shape

- WHEN a developer runs the maintained eval command
- THEN they can select a stage such as `owner_add` or `stl_extract` with one shared CLI shape
- AND case discovery, case filtering, report output, and config selection behave consistently across stages

### Requirement: Explicit Stage-Level Test Coverage

The repository SHALL organize automated eval tests so shared dataset behavior and stage-specific behavior are verified separately.

#### Scenario: Pytest Coverage Mirrors Shared And Stage-Specific Responsibilities

- WHEN eval-related pytest suites run
- THEN shared dataset loading and stage discovery are tested independently from owner-add stage behavior
- AND STL extraction stage behavior is tested in its own focused suite
