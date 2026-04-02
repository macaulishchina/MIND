# Verification Report: chat-homepage-workbench

## Metadata

- Change ID: `chat-homepage-workbench`
- Verification profile: `full`
- Status: `complete`
- Prepared by: `Codex`

## Checks Run

### `workflow-integrity`

- Result: `pass`
- Evidence:
  - Proposal created and approved in
    `.ai/changes/chat-homepage-workbench/proposal.md`
  - Change-local spec deltas added under
    `.ai/changes/chat-homepage-workbench/specs/`
  - Tasks finalized before implementation in
    `.ai/changes/chat-homepage-workbench/tasks.md`
- Notes:
  - The change followed the repository `.ai` workflow for a non-small feature.

### `change-completeness`

- Result: `pass`
- Evidence:
  - Typed config now resolves curated chat profiles from TOML in
    `mind/config/schema.py` and `mind/config/manager.py`
  - Application layer now exposes chat model discovery and chat completion in
    `mind/application/models.py` and `mind/application/service.py`
  - REST adapter now exposes `GET /api/v1/chat/models` and
    `POST /api/v1/chat/completions` in `mind/interfaces/rest/app.py`
  - Frontend is now chat-first in `frontend/src/App.tsx` and
    `frontend/src/styles.css`
- Notes:
  - The change covered config, application, REST, frontend, and docs together,
    which matches the approved scope.

## Additional Checks

### `spec-consistency`

- Result: `pass`
- Evidence:
  - Chat-completion and curated chat-profile requirements merged into
    `.ai/specs/interface-foundation/spec.md`
  - Chat-first workbench requirements merged into
    `.ai/specs/frontend-workbench/spec.md`
- Notes:
  - Current approved specs now describe the implemented behavior instead of the
    older playground-first frontend wording.

### `backend-regression`

- Result: `pass`
- Evidence:
  - `.venv/bin/python -m pytest tests/test_application_service.py tests/test_rest_api.py -q`
    -> `13 passed`
  - `.venv/bin/python -m pytest tests/`
    -> `210 passed in 10.81s`
- Notes:
  - The targeted run covered the new config/application/REST chat paths before
    the full suite was executed.

### `frontend-regression`

- Result: `pass`
- Evidence:
  - `npm run test` in `frontend/`
    -> `3 passed`
  - `npm run build` in `frontend/`
    -> success
- Notes:
  - Frontend tests cover chat send, incremental memory submit, explorer
    update/delete, and anonymous owner flow.

### `manual-smoke`

- Result: `pass`
- Evidence:
  - Started the maintained REST adapter with
    `python -m mind.interfaces.rest.run --toml mind.frontend-smoke.toml.example`
  - Recorded REST smoke artifacts in
    `.ai/changes/chat-homepage-workbench/artifacts/chat_workbench_rest_smoke_2026-04-02.md`
    and
    `.ai/changes/chat-homepage-workbench/artifacts/chat_workbench_rest_smoke_2026-04-02.json`
- Notes:
  - The manual smoke covered curated chat-model discovery, known-owner chat,
    incremental memory submits, memory CRUD/history, and anonymous-owner flow.
  - Browser-level E2E was not executed in this environment; frontend behavior is
    instead covered by Vitest/JSDOM plus the live REST smoke path.

### `human-doc-sync`

- Result: `pass`
- Evidence:
  - Updated `.ai/project.md`
  - Updated `.human/context.md`
  - Updated `.human/verification.md`
- Notes:
  - The human handbook now reflects the chat-first frontend and the maintained
    frontend verification commands.

## Residual Risk

- The frontend currently relies on local browser state to remember the
  submission cursor for “only submit new turns.” That is durable across refresh
  for one browser profile, but it is not a cross-device or server-authoritative
  guarantee.
- Browser-level live smoke was not executed in this environment. REST live
  smoke plus automated frontend tests provide strong evidence, but not a full
  visual/manual browser walkthrough.
- The fake backend used for smoke has narrow extraction heuristics. A phrasing
  such as `I also drink americano` did not extract a new memory, while
  `I drink americano` did. This affects fake smoke phrasing but not the
  correctness of the frontend incremental-submit logic itself.

## Summary

- The selected `full` profile is satisfied.
- Config, application, REST, frontend, docs, and workflow artifacts were all
  updated and verified for the new chat-first workbench contract.
