# Spec: interface-foundation

## ADDED Requirements

### Requirement: Application Layer Supports Maintained Chat Completion

The repository SHALL provide a maintained chat-completion operation in the
application layer for upper adapters.

#### Scenario: Adapter Requests Chat Completion Through Application Layer

- WHEN a maintained adapter requests an assistant reply for a conversation
- THEN it calls the application layer rather than constructing LLM access
  directly
- AND the request uses a curated chat model profile id plus a message history
- AND STL extraction and decision-stage runtime selection remain internal

### Requirement: Curated Chat Model Profiles Are Resolved From TOML

The repository SHALL resolve a frontend-selectable chat model registry from the
central TOML configuration surface.

#### Scenario: Frontend Receives Curated Chat Model Choices

- WHEN the REST adapter advertises chat model choices
- THEN it returns only the curated chat profiles defined for interactive chat
- AND it does not expose backend-only stage configs such as STL extraction or
  decision overrides

### Requirement: REST Exposes Chat Discovery And Completion

The repository SHALL expose maintained REST endpoints for chat model discovery
and chat completion above the application layer.

#### Scenario: Client Uses Versioned Chat Endpoints

- WHEN a client calls the maintained REST service for chat behavior
- THEN the service exposes versioned `/api/v1` endpoints for chat model listing
  and chat completion
- AND chat requests use the canonical owner selector contract where owner
  context is required
