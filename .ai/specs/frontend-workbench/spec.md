# Spec: frontend-workbench

## ADDED Requirements

### Requirement: Frontend Workbench Uses REST Only

The repository SHALL provide the maintained frontend workbench as a separate
project that integrates with MIND only through the maintained REST adapter.

#### Scenario: Workbench Does Not Couple To Python Internals

- WHEN the frontend performs ingestion, search, listing, update, delete, or
  history actions
- THEN it calls the maintained REST API
- AND it does not depend on direct Python imports or storage backends

### Requirement: Workbench Provides Chat Workspace And Explorer Surfaces

The repository SHALL provide a maintained internal workbench with a chat-first
workspace and a memory explorer.

#### Scenario: Chat Workspace Supports Conversation Experience

- WHEN a developer uses the main workbench homepage
- THEN they can choose a known or anonymous owner, select one of the curated
  chat model profiles, exchange chat messages with the assistant, and submit the
  active conversation to memory ingestion
- AND the frontend submits only the turns that have not already been submitted
  for the active conversation

#### Scenario: Explorer Supports Memory Inspection And Mutation

- WHEN a developer uses the `Memory Explorer`
- THEN they can list memories by owner, inspect a memory, update it, delete it,
  and view its history timeline

### Requirement: Frontend Workbench Has A Reproducible Live Smoke Path

The repository SHALL document a reproducible local live-smoke path for the
maintained frontend workbench against a running REST adapter, using a safe
configuration that does not require live model calls.

#### Scenario: Developer Runs Local Live Smoke

- WHEN a developer follows the documented frontend live-smoke path
- THEN they can start the maintained REST adapter against a safe local config
- AND they can launch the frontend workbench against that adapter
- AND they can exercise known-owner and anonymous-owner flows without requiring
  live provider credentials
