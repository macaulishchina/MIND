# Spec Delta: owner-centered-memory

## UPDATED Requirements

### Requirement: Stage-Specific LLM Overrides

The system SHALL expose stage-specific LLM overrides only for stages that remain on the current STL-native `add()` path.

#### Scenario: Active Add Path Uses STL Extraction And Decision Stages

- WHEN `Memory.add()` runs through the current STL-native pipeline
- THEN the system resolves stage-specific LLM configuration from `llm.stl_extraction` for semantic extraction and from `llm.decision` for owner-centered projection/update decisions, with fallback to the global `llm` configuration when either stage override is absent

#### Scenario: Removed Legacy Stages Are Not Surfaced As Runtime Knobs

- WHEN the configuration is used for the maintained STL-native add flow
- THEN deprecated legacy stages such as `llm.extraction` and `llm.normalization` are not part of the supported runtime stage override surface
