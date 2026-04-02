# Frontend Live Smoke Summary

- Date: `2026-04-02`
- Frontend URL: `http://127.0.0.1:5173`
- API URL: `http://127.0.0.1:18000`
- REST config: `mind.frontend-smoke.toml.example`

## Commands

```bash
python -m mind.interfaces.rest.run --toml mind.frontend-smoke.toml.example
cd frontend && VITE_API_BASE_URL=http://127.0.0.1:18000 npm run dev -- --host 127.0.0.1
curl http://127.0.0.1:18000/healthz
curl http://127.0.0.1:5173/
cd frontend && VITE_API_BASE_URL=http://127.0.0.1:18000 npm exec -- vitest --config vite.config.ts run src/__live_smoke__.test.tsx
```

## Observed Flow

- Known owner `demo-user`
  - ingestion created `[self] preference:like=black coffee`
  - search returned `1` memory item
  - update completed and the live system returned `preference:like=americano`
  - delete completed and explorer returned to `Load memories to inspect this owner.`
- Anonymous owner `anon-live-smoke-1`
  - ingestion created `[self] preference:like=green tea`
  - search returned `1` memory item

## Supporting Artifacts

- `rest_healthz.json`
- `frontend_index.html`
- `live_smoke_summary.json`

## Notes

- Browser-level Playwright automation was attempted first, but the local system
  lacked required shared libraries for Chromium (`libnspr4.so`). The final live
  smoke therefore used the real running REST service plus the real frontend
  component tree rendered through the existing Vitest/JSDOM harness.
- This still verified the maintained frontend code against a live HTTP backend;
  it did not rely on mocked `fetch`.
