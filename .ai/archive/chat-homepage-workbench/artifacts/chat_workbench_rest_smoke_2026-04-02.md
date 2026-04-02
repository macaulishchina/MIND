# Chat Workbench REST Smoke

- Date: `2026-04-02`
- Config: `mind.frontend-smoke.toml.example`
- Base URL: `http://127.0.0.1:18000`

## Commands

```bash
python -m mind.interfaces.rest.run --toml mind.frontend-smoke.toml.example
```

Then a scripted HTTP walkthrough exercised:

1. `GET /api/v1/chat/models`
2. `POST /api/v1/chat/completions`
3. `POST /api/v1/ingestions`
4. `GET /api/v1/memories`
5. `PATCH /api/v1/memories/{memory_id}`
6. `DELETE /api/v1/memories/{memory_id}`
7. `GET /api/v1/memories/{memory_id}/history`

## Result Summary

- Chat model discovery returned two curated fake profiles: `fake-default` and `fake-alt`
- Known-owner incremental submit succeeded with a two-step conversation:
  - first submit created `[self] preference:like=black coffee`
  - second submit sent only the new turn chunk and created `[self] habit:drink=americano`
  - owner list count after both submits was `2`
- Memory CRUD follow-up succeeded:
  - update returned `200`
  - delete returned `204`
  - history after delete showed `ADD -> UPDATE -> DELETE`
- Anonymous-owner chat and ingestion also succeeded:
  - chat returned `echo: I love green tea`
  - ingestion created one memory
  - owner list count was `1`

## Notes

- During exploratory smoke, the fake STL backend did not extract a new memory
  from the phrase `I also drink americano`, but it did extract one from
  `I drink americano`. This is a fake-backend heuristic boundary rather than a
  frontend incremental-submit bug, so the recorded smoke evidence uses the
  stable fake-supported phrasing.
