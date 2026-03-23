# MIND Change Protocol

> When you change A, you MUST also change B. This is the synchronization map.
>
> Last updated: 2026-03-23 — Project reset to v0.0.0 (fresh start)

---

## Status

Change protocols are **not yet defined** for the new architecture.
This file will be populated as modules and interfaces are created.

The following general protocol always applies:

---

## 1. Planning a Large Change

| Step | File(s) to change |
|------|--------------------|
| 1. Create or update a repo-root plan | `PLANS.md` from `.ai/templates/PLANS.md` |
| 2. Record scope and constraints | Goal, constraints, non-goals, affected areas |
| 3. Break work into verifiable slices | `## Steps` + `## Verification` |
| 4. Keep plan current during execution | `## Progress Log`, `## Decisions`, `## Open Questions` |
| 5. Close or archive the plan after the work lands | Update final status and follow-ups |

---

## 2. Verification Checklist (After Any Change)

- [ ] `uv run ruff check` — zero errors
- [ ] `uv run mypy` — zero errors
- [ ] `uv run pytest` — all tests pass
- [ ] Changed code has corresponding test(s)
- [ ] No new `# type: ignore` without justification
- [ ] If the change introduced a new sync dependency, update this file