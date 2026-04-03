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

### Requirement: Dedicated Decision Prompt Evaluation Workflow

The repository SHALL maintain a dedicated evaluation workflow for
`UPDATE_DECISION_SYSTEM_PROMPT` instead of relying only on coarse
`owner_add` end-to-end outcomes.

#### Scenario: Decision Prompt Quality Is Evaluated Directly

- WHEN engineers need to compare decision prompt variants
- THEN they can run a direct decision-stage harness over canonical memory cases
- AND the report captures JSON parse success, action quality, temp-id grounding,
  text-constraint pass rate, and protected-case regressions separately from
  extraction or retrieval noise

### Requirement: Offline-Gated Prompt Self-Optimization

The repository SHALL keep prompt self-optimization for decision prompts offline
and gate it with explicit promotion checks.

#### Scenario: Candidate Prompt Iteration Stays Offline

- WHEN engineers run the maintained decision prompt optimization campaign
- THEN candidate prompts are generated and evaluated offline against the
  decision dataset
- AND promotion requires explicit non-regression gates plus a positive quality
  gain
- AND runtime prompt text is never self-modified during normal production calls
