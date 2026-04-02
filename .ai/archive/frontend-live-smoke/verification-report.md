# Verification Report: frontend-live-smoke

## Metadata

- Change ID: `frontend-live-smoke`
- Verification profile: `full`
- Status: `complete`
- Prepared by: `agent`

## Checks Run

### `workflow-integrity`

- Result: `pass`
- Evidence:
  - Proposal created and approved in
    `.ai/archive/frontend-live-smoke/proposal.md`
  - Change-local spec delta created in
    `.ai/archive/frontend-live-smoke/specs/frontend-workbench/spec.md`
  - Tasks, artifacts, and this verification report were completed before archive
- Notes:
  - The change stayed scoped to the smoke path, launcher/config support, and
    archived integration evidence

### `change-completeness`

- Result: `pass`
- Evidence:
  - Added the tracked smoke config:
    - `mind.frontend-smoke.toml.example`
  - Added launcher support for explicit TOML selection:
    - `mind/interfaces/rest/run.py`
  - Updated smoke-facing docs:
    - `README.md`
    - `frontend/README.md`
    - `mind/interfaces/rest/README.md`
  - Added archived smoke artifacts:
    - `frontend_index.html`
    - `rest_healthz.json`
    - `live_smoke_summary.json`
    - `live_smoke_2026-04-02.md`
- Notes:
  - The change did not broaden into a permanent browser-E2E framework decision

## Additional Checks

### `spec-consistency`

- Result: `pass`
- Evidence:
  - Change-local delta:
    `.ai/archive/frontend-live-smoke/specs/frontend-workbench/spec.md`
  - Living spec:
    `.ai/specs/frontend-workbench/spec.md`
  - The documented smoke path now matches the implementation:
    - `python -m mind.interfaces.rest.run --toml mind.frontend-smoke.toml.example`
    - `VITE_API_BASE_URL=http://127.0.0.1:18000 npm run dev`
- Notes:
  - The smoke path uses a safe local config rather than changing the meaning of
    the normal `mind.toml` runtime path

### `human-doc-sync`

- Result: `pass`
- Evidence:
  - `.ai/project.md` now records the maintained frontend live-smoke path as a
    stable repository fact
  - `.human/context.md` now explains that frontend/REST live smoke can be rerun
    without live provider credentials
- Notes:
  - `.human/verification.md` did not need changes because the verification model
    itself did not change

### `manual-review`

- Result: `pass`
- Evidence:
  - Reviewed `mind.frontend-smoke.toml.example` to confirm it stays on
    fake/local components only
  - Reviewed docs to confirm the smoke commands consistently point at the smoke
    TOML and port `18000`
  - Reviewed the live smoke artifacts to confirm they match the documented
    known-owner and anonymous-owner flows
- Notes:
  - A real integration nuance was preserved in the artifact summary: the fake
    backend returned `preference:like=americano` on update rather than the
    bracketed form used in mocked frontend fixtures

### `automated-regression`

- Result: `pass`
- Evidence:
  - `.venv/bin/python -m pytest tests/test_application_service.py -q`
    - `5 passed`
  - `.venv/bin/python -m pytest tests/test_rest_run.py -q`
    - `2 passed`
  - `.venv/bin/python -m pytest tests/test_rest_api.py -q`
    - `4 passed`
  - `.venv/bin/python -m pytest tests/`
    - `205 passed in 12.51s`
  - `PATH=/tmp/node-v22/bin:$PATH /tmp/node-v22/bin/npm run test`
    - `3 passed`
  - `PATH=/tmp/node-v22/bin:$PATH /tmp/node-v22/bin/npm run build`
    - production build completed successfully
- Notes:
  - Frontend test/build were rerun even though the frontend code path did not
    change materially, to keep the workbench baseline current alongside the
    smoke-path changes

### `live-smoke-evidence`

- Result: `pass`
- Evidence:
  - `curl -sSf http://127.0.0.1:18000/healthz`
    - captured in `rest_healthz.json`
  - `curl -sSf http://127.0.0.1:5173/`
    - captured in `frontend_index.html`
  - `VITE_API_BASE_URL=http://127.0.0.1:18000 npm exec -- vitest --config vite.config.ts run src/__live_smoke__.test.tsx`
    - `1 passed`
  - Live smoke summary captured in:
    - `live_smoke_summary.json`
    - `live_smoke_2026-04-02.md`
- Notes:
  - The live smoke exercised a running REST server plus the real frontend
    component tree with unmocked HTTP calls

## Residual Risk

- Browser-level Playwright automation could not run in this environment because
  Chromium was missing a required shared library (`libnspr4.so`); the archived
  smoke therefore uses the running REST service plus the Vitest/JSDOM-rendered
  frontend component tree instead of a full browser
- The smoke config is intentionally local and fake-backed, so it does not prove
  behavior against live providers or production infrastructure
- The smoke path writes temporary local SQLite files during execution; the
  verification run cleaned them up, but developers rerunning the path locally
  may still generate ignored local artifacts

## Summary

- The selected `full` profile is satisfied
- The main accepted limitation is that the final live smoke evidence is
  frontend-component + live-REST integration rather than full browser-E2E
