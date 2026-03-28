# Capability: Memory Add Extraction

## Current Requirements

### Requirement: Extraction Stage Contract

The system SHALL keep the extraction stage compatible with the MVP runtime contract by returning a list of fact objects with `text` and `confidence` fields.

#### Scenario: Extraction Output Is Cleaned Before Downstream Use

- WHEN the extraction model returns empty rows, malformed rows, duplicate rows, or invalid confidence values
- THEN the system normalizes whitespace and trailing punctuation, clamps confidence into `[0.0, 1.0]`, drops invalid rows, and keeps only the highest-confidence exact duplicate before retrieval and decision begin

#### Scenario: Extraction Drops Obvious Noise Before Downstream Use

- WHEN the extraction model returns fact candidates that are clearly temporary troubleshooting chatter, attributed advice from other people, or speculative future statements
- THEN the system drops those candidates before retrieval and decision begin while preserving committed future plans and stable user-owned facts

#### Scenario: Extraction Canonicalizes High-Frequency Preference Patterns

- WHEN the extraction model returns semantically equivalent phrasing for short-answer preferences, list-format preferences, English-summary preferences, or obvious `no longer` drink-preference updates
- THEN the system rewrites them into a stable canonical fact string before retrieval and decision begin

### Requirement: Extraction Stage Control Surface

The system SHALL allow the extraction stage to override the LLM temperature independently from the default per-model temperature.

#### Scenario: Extraction Temperature Override Is Configured

- WHEN `llm.extraction_temperature` is set in configuration
- THEN the extraction LLM call uses that temperature value without changing the default temperature used by other LLM calls

### Requirement: Extraction Prompt Guidance

The system SHALL provide explicit extraction guidance for atomic facts, exclusions, and confidence scoring.

#### Scenario: Prompt Targets Atomic User Facts

- WHEN the extraction prompt is sent to the model
- THEN it includes clear extraction scope, exclusions for assistant content, speculative content, transient troubleshooting noise, externally attributed advice, and weak identity or language inference from single-message evidence, plus at least one positive and one negative example

### Requirement: Extraction Evaluation Dataset Topology

The repository SHALL keep the top-level difficulty-layered extraction regression datasets separate from any standalone black-box holdout dataset.

#### Scenario: Default Regression Discovery Uses Difficulty-Layered Datasets

- WHEN `tests/eval/runners/eval_extraction.py` runs without an explicit `--dataset` path
- THEN it evaluates the top-level difficulty-layered extraction datasets and does not implicitly include the standalone black-box holdout dataset stored outside top-level discovery

#### Scenario: Black-Box Holdout Runs Explicitly

- WHEN the evaluator is run with an explicit `--dataset` path that points to the standalone black-box holdout file
- THEN it evaluates that holdout dataset and emits the same report structure as the difficulty-layered datasets