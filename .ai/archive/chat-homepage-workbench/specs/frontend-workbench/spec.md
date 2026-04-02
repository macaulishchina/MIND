# Spec: frontend-workbench

## MODIFIED Requirements

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
