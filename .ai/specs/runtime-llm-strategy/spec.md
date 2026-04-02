# Spec: runtime-llm-strategy

### Purpose

- Define the maintained default online STL extraction runtime profile so
  config, docs, and future changes share the same baseline assumptions.

### Requirements

### Requirement: Default Online STL Extraction Profile

The repository SHALL maintain one documented default online STL extraction
profile for the `Memory.add()` runtime path.

#### Scenario: Default Runtime Uses The Maintained Extraction Profile

- WHEN a developer uses the maintained repository default config without adding
  their own stage override
- THEN the STL extraction stage resolves independently from the general LLM
  default
- AND it uses the current maintained online extraction model/profile rather
  than inheriting the decision-stage default by accident

### Requirement: Base Prompt Remains The Online Default

The repository SHALL keep the base STL extraction prompt as the maintained
online default unless a different prompt mode is explicitly selected.

#### Scenario: Supplement Is Not Implicitly Enabled

- WHEN the maintained default runtime config is loaded
- THEN `prompts.stl_extraction_supplement` resolves to `false`
- AND STL extraction uses the base prompt without automatically appending the
  supplement block

### Requirement: Stage-Specific Timeout Is Configurable

The repository SHALL allow a maintained STL extraction stage override to carry
its own normal request timeout.

#### Scenario: Extraction Timeout Differs From Global Default

- WHEN the maintained config sets a timeout on `llm.stl_extraction`
- THEN the resolved `llm_stages["stl_extraction"]` config includes that timeout
- AND the extraction client uses that stage-specific timeout instead of the
  global default request timeout
