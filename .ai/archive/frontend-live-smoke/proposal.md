# Change Proposal: Frontend Live Smoke

## Metadata

- Change ID: `frontend-live-smoke`
- Type: `feature`
- Status: `archived`
- Spec impact: `update required`
- Verification profile: `full`
- Owner: `agent`
- Related specs: `frontend-workbench`, `interface-foundation`

## Summary

- Add a reproducible local live-smoke path for the internal frontend workbench
  against the maintained REST adapter, and archive one successful end-to-end
  smoke run as durable evidence.

## Why Now

- The repository now has the application layer, REST adapter, and independent
  frontend workbench, but the current evidence stops at mocked frontend tests
  plus backend API tests.
- Before v1.5 begins, the project needs one real integration proof that the UI
  can talk to the running REST service instead of only passing isolated tests.
- A maintained smoke path should avoid live model cost and provider variance so
  future reruns stay cheap and reliable.

## In Scope

- Add a safe local smoke configuration for REST + frontend integration.
- Make the REST launcher easy to point at a non-default TOML file.
- Document the live smoke commands for backend and frontend local development.
- Run one successful live smoke and archive the evidence.

## Out Of Scope

- Converting the live smoke into a required CI gate.
- Adding MCP or CLI smoke coverage.
- Adding auth, deployment automation, or browser-E2E infrastructure as a
  maintained dependency.
- Changing core memory semantics, STL behavior, or prompt strategy.

## Proposed Changes

### 1. Add a safe local smoke path

- Introduce a tracked TOML template dedicated to local frontend/REST smoke.
- Keep it on fake/local components so the smoke path does not require live
  model credentials or external vector infrastructure.

### 2. Make the REST launcher smoke-friendly

- Allow `python -m mind.interfaces.rest.run` to accept an explicit TOML path so
  the documented smoke flow can launch the maintained adapter without ad hoc
  Python snippets.

### 3. Capture one successful live integration record

- Run the REST adapter and frontend together locally.
- Exercise known-owner and anonymous-owner flows through the frontend surface.
- Archive the command path and observed outcomes as the first durable frontend
  live-smoke record.

## Reality Check

- Using `mind.toml` for this smoke would accidentally turn an integration check
  into a live-provider test with avoidable nondeterminism and token spend.
- The current REST launcher assumes the default TOML, which makes safe local
  smoke awkward unless the user hand-writes Python to inject config.
- A full browser-E2E framework could be added, but that is a bigger long-term
  testing decision. The narrower need right now is a reproducible local smoke
  path plus archived proof that it worked once.
- The smoke should validate the maintained UI path without claiming stronger
  guarantees than it actually covers; it remains complementary to the existing
  deterministic test suites.

## Acceptance Signals

- A tracked safe smoke config exists for local frontend/REST integration.
- The REST launcher can be pointed at that config via normal CLI invocation.
- Repo docs explain how to run the backend and frontend together in smoke mode.
- Archived evidence shows one successful live smoke covering:
  - known-owner ingestion/search/update/delete/history
  - anonymous-owner ingestion/search

## Verification Plan

- Profile: `full`
- Automated evidence:
  - targeted regression for any CLI/config changes
  - `.venv/bin/python -m pytest tests/`
- Manual evidence:
  - start REST with the smoke config
  - start the frontend workbench
  - run the agreed known/anonymous flows and archive the result
- Required checks: `workflow-integrity`, `change-completeness`,
  `spec-consistency`, `manual-review`, `automated-regression`,
  `live-smoke-evidence`, `human-doc-sync`

## Open Questions

- None blocking. The smoke will stay local, fake-backed, and intentionally
  narrower than a production-grade browser test strategy.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
