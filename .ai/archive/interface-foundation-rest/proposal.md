# Change Proposal: Interface Foundation and REST Adapter

## Metadata

- Change ID: `interface-foundation-rest`
- Type: `feature`
- Status: `archived`
- Spec impact: `update required`
- Verification profile: `full`
- Owner: `agent`
- Related specs: `interface-foundation`, `owner-centered-memory`

## Summary

- Add a repository-internal application layer above `mind.Memory` and expose
  the first maintained external adapter as a REST API.

## Why Now

- The repository has an implemented memory kernel, but no stable service layer
  for future REST / MCP / CLI adapters to share.
- A frontend workbench is planned immediately after this change, and it needs a
  maintained interface that is not coupled directly to `mind.Memory`.
- Current public behavior is still split between owner-centered `add()` and
  compatibility-style `user_id` retrieval methods; this is the right time to
  normalize the upper-layer contract around owner selectors.

## In Scope

- Add `mind/application/` as the maintained application/service layer.
- Define shared request/response DTOs for owner selection and memory
  operations.
- Add the first REST adapter under `mind/interfaces/rest/`.
- Add REST configuration to the resolved config schema.
- Add deterministic application-layer and REST tests using fake backends.
- Update docs for REST usage and local API development.
- Reserve architecture positions for `mind/interfaces/mcp/` and
  `mind/interfaces/cli/`.

## Out Of Scope

- MCP implementation.
- CLI implementation.
- Auth, multi-tenant access control, streaming, WebSocket, or deployment
  automation.
- Changing the core STL pipeline or memory semantics.
- Frontend implementation; that follows in `frontend-workbench`.

## Proposed Changes

### 1. Add a canonical application layer

- Introduce a `MindService` that becomes the only maintained upper-layer entry
  point for adapters.
- Introduce canonical owner-based DTOs so adapters do not expose the legacy
  `user_id` retrieval style directly.

### 2. Ship the first REST adapter

- Add a FastAPI app with a shared service instance and a fixed `/api/v1`
  surface for health, capabilities, ingestion, CRUD, search, and history.
- Map owner-selector and not-found failures into explicit HTTP responses.

### 3. Make REST configurable and testable

- Extend config resolution with a `rest` section for host, port, and CORS.
- Add deterministic tests with fake backends so the REST layer joins the normal
  pytest regression baseline without requiring live model calls.

## Reality Check

- The current kernel is still shaped around `Memory`; the new application layer
  should wrap it, not try to redesign the core data model during the same
  change.
- Because `search()` and `get_all()` still accept `user_id`, the canonical
  owner contract must be normalized in the application layer first. Pushing
  that mismatch up into REST would freeze the wrong interface.
- FastAPI is not currently a repository dependency, so this change must add the
  runtime dependency and deterministic tests together.
- The environment currently has no Node toolchain; that does not block this
  backend change, but it does mean the follow-up frontend change may need to
  carry an explicit verification limitation if Node remains unavailable.

## Acceptance Signals

- `mind/application/` exists and adapters can call `MindService` without
  importing `mind.memory.Memory`.
- A maintained FastAPI app exists with the agreed REST endpoints and config
  surface.
- Deterministic pytest coverage exists for owner selector validation and the
  REST happy/error paths.
- Docs explain how to start and use the REST API locally.

## Verification Plan

- Profile: `full`
- Automated evidence:
  - `.venv/bin/python -m pytest tests/`
  - targeted REST/application tests when helpful during iteration
- Manual evidence:
  - review README and local API docs for command correctness
  - review architecture boundaries to ensure adapters do not import
    `mind.memory.Memory` directly
- Required checks: `workflow-integrity`, `change-completeness`,
  `spec-consistency`, `manual-review`, `automated-regression`

## Open Questions

- None blocking. The change follows the approved plan and keeps the service
  contract intentionally thin over the existing kernel.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
