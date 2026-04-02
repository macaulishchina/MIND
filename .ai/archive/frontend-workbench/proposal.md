# Change Proposal: Frontend Workbench

## Metadata

- Change ID: `frontend-workbench`
- Type: `feature`
- Status: `archived`
- Spec impact: `update required`
- Verification profile: `full`
- Owner: `agent`
- Related specs: `frontend-workbench`, `interface-foundation`

## Summary

- Add a repository-local React + Vite workbench for internal experience and
  testing of MIND through the maintained REST API.

## Why Now

- The repository now has a maintained application layer and REST adapter, so a
  frontend can be built on a stable upper interface instead of coupling to the
  Python kernel.
- The MVP needs a practical experience and testing surface before v1.5 quality
  work begins.
- A workbench will make owner-centered ingestion, search, CRUD, and history
  behavior observable without requiring direct Python scripting.

## In Scope

- Add a standalone `frontend/` React + Vite + TypeScript project in this repo.
- Implement two workbench surfaces: `Playground` and `Memory Explorer`.
- Route all frontend behavior through the maintained REST API only.
- Add frontend unit/integration-style tests with mocked REST calls.
- Update repo docs for frontend setup and local development.

## Out Of Scope

- Auth, multi-user roles, deployment automation, or production hosting.
- Server-side rendering, Next.js, or backend-rendered pages.
- Direct browser access to Python internals or database backends.
- MCP / CLI UIs.

## Proposed Changes

### 1. Add a standalone internal workbench

- Create a repo-local frontend project with its own package metadata and Vite
  build/test setup.
- Keep it independent from the Python package layout and configure it with only
  `VITE_API_BASE_URL`.

### 2. Implement the two required user surfaces

- `Playground`: owner selection, multi-message ingestion, created-memory
  results, and semantic search.
- `Memory Explorer`: owner-scoped listing, detail view, manual update, delete,
  and history timeline.

### 3. Verify the UI against the REST contract

- Mock REST responses in frontend tests instead of depending on live services.
- Document the local flow for running REST + frontend together as the internal
  workbench path.

## Reality Check

- The environment did not start with a system Node toolchain, so frontend
  verification may require a local Node bootstrap path rather than assuming
  machine-global install state.
- This workbench is for internal use; designing it as a polished public product
  shell would add cost without improving the immediate testing surface.
- The frontend should not invent richer semantics than the REST API currently
  exposes. If a desired interaction is missing, the right answer is to stay
  within the REST contract defined by `interface-foundation-rest`.

## Acceptance Signals

- `frontend/` exists as a standalone React + Vite + TypeScript project.
- The workbench supports the planned playground and explorer flows only through
  REST.
- Frontend tests cover ingestion, search, listing, update, delete, and history
  rendering.
- Repo docs explain how to run the backend and frontend together locally.

## Verification Plan

- Profile: `full`
- Automated evidence:
  - frontend install/test/build commands
  - `.venv/bin/python -m pytest tests/`
- Manual evidence:
  - review the workbench to ensure it only calls REST endpoints
  - review responsive layout and page separation
- Required checks: `workflow-integrity`, `change-completeness`,
  `spec-consistency`, `manual-review`, `automated-regression`

## Open Questions

- None blocking. The frontend scope is intentionally limited to the approved
  internal workbench.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
