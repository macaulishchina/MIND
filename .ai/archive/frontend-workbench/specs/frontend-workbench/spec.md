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

### Requirement: Workbench Provides Playground And Explorer Surfaces

The repository SHALL provide two maintained internal workbench surfaces.

#### Scenario: Playground Supports Conversation Experience

- WHEN a developer uses the `Playground`
- THEN they can choose a known or anonymous owner, edit multiple messages,
  submit ingestion requests, and run search against the same owner context

#### Scenario: Explorer Supports Memory Inspection And Mutation

- WHEN a developer uses the `Memory Explorer`
- THEN they can list memories by owner, inspect a memory, update it, delete it,
  and view its history timeline
