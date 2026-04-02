# Spec: interface-foundation

## ADDED Requirements

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
