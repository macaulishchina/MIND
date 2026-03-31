# Spec: owner-centered-memory

## ADDED Requirements

### Requirement: Owner-Centered Add Interface

The system SHALL resolve each `add()` call to a durable owner using either a known external user identifier or a persistent anonymous session identifier.

#### Scenario: Known Owner Is Resolved From Business Identifier

- WHEN `add()` is called with a known owner context carrying `external_user_id`
- THEN the system resolves or creates one durable owner record for that external identifier and stores new memories under that resolved owner

#### Scenario: Anonymous Owner Is Persisted Across Sessions

- WHEN `add()` is called with an owner context carrying `anonymous_session_id`
- THEN the system resolves or creates one durable anonymous owner record for that session identifier and stores new memories under that resolved owner

#### Scenario: Legacy User ID Remains Accepted

- WHEN `add()` is called with the legacy `user_id` argument
- THEN the system treats it as a compatibility alias for a known owner external identifier

### Requirement: Owner-Local Subject References

The system SHALL assign each extracted fact to a subject reference within the current owner space.

#### Scenario: Self Facts Use The Self Subject Reference

- WHEN the extracted fact is about the current owner
- THEN the system assigns `subject_ref = "self"`

#### Scenario: Named Third-Party Facts Use Relation-And-Name References

- WHEN the extracted fact is about a named third-party object related to the owner
- THEN the system assigns a subject reference shaped like `<relation>:<normalized_name>` and reuses it for later matching facts with the same owner, relation, and normalized name

#### Scenario: Unnamed Third-Party Facts Use Owner-Local Placeholders

- WHEN the extracted fact is about an unnamed third-party object related to the owner
- THEN the system assigns an owner-local placeholder subject reference shaped like `<relation>:unknown_<n>`

### Requirement: Structured Fact Envelopes

The system SHALL normalize extracted facts into structured envelopes before storage.

#### Scenario: Envelope Carries Canonical Fact Metadata

- WHEN a raw fact is normalized
- THEN the resulting envelope includes owner identity, subject reference, fact family, field key, canonical text, raw text, confidence, and source context fields

### Requirement: Canonical Structured Text Storage

The system SHALL store canonical structured text derived from the structured envelope instead of unconstrained natural-language memory text.

#### Scenario: Canonical Text Uses A Fixed Machine-Friendly Template

- WHEN a normalized fact envelope is persisted
- THEN the stored memory content follows a fixed structured-text template such as `[self] name=John` or `[friend:green] occupation=football player`

### Requirement: Owner-Aware Candidate Retrieval

The system SHALL narrow update candidates by owner, subject reference, fact family, and field key before semantic ranking.

#### Scenario: Retrieval Does Not Mix Different Owner Subjects

- WHEN deciding whether a new normalized fact should add or update memory
- THEN the system only considers candidate memories that share the resolved owner and matching structured context filters before semantic similarity ranking is applied

### Requirement: Stage-Specific LLM Overrides

The system SHALL allow stage-specific LLM overrides only for stages that remain on the STL-native `add()` path, with fallback to the global LLM configuration.

#### Scenario: Unconfigured Active Stage Falls Back To Global LLM

- WHEN a stage-specific LLM override is absent
- THEN the system uses the global resolved LLM configuration for that stage

#### Scenario: Active Add Path Uses STL Extraction And Decision Stages

- WHEN `Memory.add()` runs through the current STL-native pipeline
- THEN the system resolves stage-specific LLM configuration from `llm.stl_extraction` for semantic extraction and from `llm.decision` for owner-centered projection/update decisions

#### Scenario: Removed Legacy Stages Are Not Supported Runtime Knobs

- WHEN deprecated legacy stages such as `llm.extraction` or `llm.normalization` appear in configuration
- THEN the system does not treat them as part of the supported runtime stage override surface for the maintained add flow
