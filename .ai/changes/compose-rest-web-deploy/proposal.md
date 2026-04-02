# Change Proposal: Compose REST and Web Deployment

## Metadata

- Change ID: `compose-rest-web-deploy`
- Type: `feature`
- Status: `approved`
- Spec impact: `update required`
- Verification profile: `full`
- Owner: `agent`
- Related specs: `interface-foundation`, `frontend-workbench`

## Summary

- Fix the current pgvector startup failure and add a Docker Compose deployment
  path that can bring up the maintained REST API and frontend workbench with
  their prerequisites.

## Why Now

- The current REST startup path can fail immediately under the default
  `Postgres + pgvector` configuration because of a pgvector DDL formatting bug.
- The project now has a maintained REST layer and a maintained frontend
  workbench, but no containerized path for bringing them up together quickly.
- Before v1.5 begins, the repository should have a practical deployment story
  for local integration and demos, not just Python + Node commands.

## In Scope

- Fix the pgvector collection-creation bug that breaks REST startup.
- Add backend and frontend container build definitions.
- Rework `compose.yaml` so `rest` can pull up its datastore prerequisites and
  `web` can pull up `rest` plus its prerequisites.
- Keep the frontend container independent from Python internals and route it to
  the maintained REST API.
- Update docs for compose-based startup.

## Out Of Scope

- Kubernetes, Helm, or production orchestration.
- Auth, TLS termination, secrets management, or deployment hardening.
- MCP / CLI containers.
- Replacing the existing local dev commands for Python or Vite.
- Live-model provider setup automation.

## Proposed Changes

### 1. Repair the current pgvector startup path

- Fix the SQL composition in `PgVectorStore.create_collection()` so the default
  `pgvector`-backed REST service can boot successfully.

### 2. Containerize the maintained backend and web workbench

- Add a backend image that runs the maintained REST adapter.
- Add a frontend image that serves the built workbench and proxies API traffic
  to the REST service.

### 3. Organize Compose around dependency pull-up

- Make `postgres` the shared database prerequisite.
- Make `rest` depend on `postgres`.
- Make `web` depend on `rest`, so `docker compose up web` also brings up the
  API and datastore path it needs.
- Keep optional services like `qdrant` separate so they do not inflate the
  default `web/rest` path unnecessarily.

## Reality Check

- The existing `compose.yaml` only provisions infrastructure; adding `rest/web`
  containers without fixing the pgvector bug would still leave the default path
  broken.
- A production-grade deployment story would need auth, secrets handling, and
  observability, but that is much broader than the immediate “quickly boot the
  maintained web + REST surfaces” need.
- The frontend currently assumes a configurable API base URL. In containers, the
  cleanest path is to serve static assets and reverse-proxy `/api/` to REST so
  browsers do not need to know the internal service hostname.
- The compose organization should privilege the default PostgreSQL + pgvector
  path because that is the repo’s maintained MVP recommendation; Qdrant can stay
  optional.

## Acceptance Signals

- `python -m mind.interfaces.rest.run` no longer crashes on the pgvector table
  bootstrap path.
- The repository has Dockerfiles and a compose layout that can start:
  - `postgres`
  - `rest`
  - `web`
- Starting `web` also starts `rest` and `postgres`.
- Docs explain how to boot the stack and what config file is required.

## Verification Plan

- Profile: `full`
- Automated evidence:
  - targeted regression for pgvector and launcher changes
  - frontend test/build
  - `.venv/bin/python -m pytest tests/`
  - `docker compose config`
- Manual evidence:
  - inspect the resolved compose graph for `web -> rest -> postgres`
  - if docker is available, smoke `docker compose up` for the stack
- Required checks: `workflow-integrity`, `change-completeness`,
  `spec-consistency`, `manual-review`, `automated-regression`,
  `container-config-validation`, `human-doc-sync`

## Open Questions

- None blocking. The compose path will target the maintained default
  PostgreSQL-backed deployment and keep Qdrant optional.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
