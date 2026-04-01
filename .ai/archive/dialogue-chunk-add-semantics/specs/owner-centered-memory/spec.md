# Spec: owner-centered-memory

## MODIFIED Requirements

### Requirement: Owner-Centered Add Interface

The system SHALL resolve each `add()` call to a durable owner using either a known external user identifier or a persistent anonymous session identifier, and SHALL treat the `messages` argument as one newly submitted dialogue chunk regardless of how many turns it contains.

#### Scenario: Known Owner Is Resolved From Business Identifier

- WHEN `add()` is called with a known owner context carrying `external_user_id`
- THEN the system resolves or creates one durable owner record for that external identifier
- AND it stores the chunk's resulting memories under that resolved owner

#### Scenario: Anonymous Owner Is Persisted Across Sessions

- WHEN `add()` is called with an owner context carrying `anonymous_session_id`
- THEN the system resolves or creates one durable anonymous owner record for that session identifier
- AND it stores the chunk's resulting memories under that resolved owner

#### Scenario: Add Operates On One Submitted Dialogue Chunk

- WHEN `add()` is called with multiple ordered chat messages from the same newly submitted dialogue chunk
- THEN the system performs one STL extraction and one projection flow for that chunk
- AND it does not derive additional runtime calls from the number of turns inside the chunk

#### Scenario: Legacy User ID Remains Accepted

- WHEN `add()` is called with the legacy `user_id` argument
- THEN the system treats it as a compatibility alias for a known owner external identifier

### Requirement: Canonical Structured Text Storage

The system SHALL store canonical structured text derived from the structured envelope instead of unconstrained natural-language memory text, and SHALL project only the chunk-final current statements into owner memories.

#### Scenario: Canonical Text Uses A Fixed Machine-Friendly Template

- WHEN a normalized fact envelope is persisted
- THEN the stored memory content follows a fixed structured-text template such as `[self] name=John` or `[friend:green] occupation=football player`

#### Scenario: Batch-Internal Corrections Do Not Leave Intermediate Owner Memories

- WHEN a later statement in the same submitted chunk supersedes an earlier statement from that chunk
- THEN only the chunk-final current statement is projected into owner memories
- AND superseded statements from the same chunk do not produce surviving intermediate owner-memory versions
