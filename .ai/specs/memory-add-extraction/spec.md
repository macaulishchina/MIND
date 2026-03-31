# Capability: Memory Add Extraction

## Current Requirements

### Requirement: Extraction Stage Contract

The system SHALL keep the extraction stage helper compatible with the legacy MVP contract by returning a list of fact objects with `text` and `confidence` fields.

#### Scenario: Extraction Output Is Cleaned Before Downstream Use

- WHEN the extraction model returns empty rows, malformed rows, duplicate rows, or invalid confidence values
- THEN the system normalizes whitespace and trailing punctuation, clamps confidence into `[0.0, 1.0]`, drops invalid rows, and keeps only the highest-confidence exact duplicate before downstream helper callers consume the result

#### Scenario: Extraction Drops Obvious Noise Before Downstream Use

- WHEN the extraction model returns fact candidates that are clearly temporary troubleshooting chatter, attributed advice from other people, or speculative future statements
- THEN the system drops those candidates before downstream helper callers consume the result while preserving committed future plans and stable user-owned facts

#### Scenario: Extraction Canonicalizes High-Frequency Preference Patterns

- WHEN the extraction model returns semantically equivalent phrasing for short-answer preferences, list-format preferences, English-summary preferences, or obvious `no longer` drink-preference updates
- THEN the system rewrites them into a stable canonical fact string before downstream helper callers consume the result

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
