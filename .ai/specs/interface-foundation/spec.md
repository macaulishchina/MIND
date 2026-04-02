# Spec: interface-foundation

### Purpose

- Define the maintained interface foundation above `mind.Memory` so upper
  adapters share one application layer and one canonical owner-based contract.

### Requirements

### Requirement: Application Layer Is The Maintained Adapter Entry Point

The repository SHALL provide one maintained application layer above
`mind.Memory` for upper adapters.

#### Scenario: Adapters Depend On The Application Layer

- WHEN a maintained upper interface such as REST, MCP, or CLI is implemented
- THEN it calls the application layer rather than importing `mind.memory.Memory`
  directly
- AND the application layer owns the canonical owner-selector contract exposed
  to those adapters

### Requirement: Canonical Owner Selector Contract

The repository SHALL expose owner identity to maintained adapters through one
canonical selector shape.

#### Scenario: Owner Selector Uses Exactly One Identity Mode

- WHEN an adapter submits a request into the maintained application layer
- THEN it provides exactly one of `external_user_id` or
  `anonymous_session_id`
- AND invalid or conflicting owner selectors are rejected before reaching the
  core memory kernel

### Requirement: REST Is The First Maintained Upper Adapter

The repository SHALL provide a maintained REST adapter as the first external
interface above the application layer.

#### Scenario: REST Exposes Versioned Memory Operations

- WHEN a client calls the maintained REST service
- THEN the service exposes a versioned `/api/v1` surface for health,
  capabilities, ingestion, memory CRUD, search, and history
- AND it uses the canonical owner selector contract instead of exposing legacy
  `user_id` request shapes directly

### Requirement: REST Runtime Config Is Resolved From TOML

The repository SHALL resolve REST runtime settings from the central TOML
configuration surface.

#### Scenario: REST Uses Resolved Host Port And CORS Settings

- WHEN the REST adapter starts from the maintained config
- THEN it receives resolved `host`, `port`, and `cors_allowed_origins`
  settings from the typed config layer

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
