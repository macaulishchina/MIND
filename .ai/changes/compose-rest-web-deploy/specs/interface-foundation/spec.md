# Spec: interface-foundation

## ADDED Requirements

### Requirement: Compose Deployment Supports Maintained REST Startup

The repository SHALL provide a Compose-managed deployment path for the
maintained REST adapter that can boot with its required datastore prerequisites.

#### Scenario: Developer Starts REST Through Compose

- WHEN a developer starts the maintained `rest` service through Compose
- THEN Compose also starts the required datastore prerequisite services
- AND the REST container runs the maintained application layer and REST adapter
- AND the default Compose-managed REST config source is the workspace
  `mind.toml`, unless an explicit alternate TOML path is selected
