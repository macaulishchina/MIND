# Spec: frontend-workbench

## ADDED Requirements

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
