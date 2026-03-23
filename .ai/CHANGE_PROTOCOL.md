# Change Protocol

> Use this file to capture synchronization rules: when changing A, also inspect B.

---

## Status

The initial scaffold does not define any repo-specific sync rules yet.
Add entries only when a real dependency is discovered.

## Always

1. For any large or multi-step change, create or update the repo-root
   `PLANS.md` from `.ai/templates/PLANS.md`.
2. Make changes in small, verifiable slices.
3. Update nearby docs, plans, and instructions when code or workflow changes
   would otherwise make them stale.

## Sync Map

| When you change... | Also inspect... | Why |
|--------------------|-----------------|-----|
| Working rules in `.ai/CONSTITUTION.md` | Related checklists and plans | Keep guidance consistent |
| Durable architecture decisions | `.ai/ARCHITECTURE.md` and `.ai/CURRENT_STATE.md` | Preserve shared context |

## Verification

- Run whatever verification commands the repo currently supports.
- If no automation exists yet, record the manual checks you performed.
- If you discover a new recurring dependency between files, add it here.
