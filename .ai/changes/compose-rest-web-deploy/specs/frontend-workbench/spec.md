# Spec: frontend-workbench

## ADDED Requirements

### Requirement: Compose Deployment Supports Maintained Web Startup

The repository SHALL provide a Compose-managed deployment path for the
maintained frontend workbench.

#### Scenario: Developer Starts Web Through Compose

- WHEN a developer starts the maintained `web` service through Compose
- THEN Compose also starts the maintained `rest` service and its prerequisites
- AND the frontend is served as a standalone web surface that talks only to the
  maintained REST API
