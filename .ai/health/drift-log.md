# AI Governance Drift Log

> Record rule violations, blind spots, and rule conflicts found during AI-driven development.

---

## Format

```
### YYYY-MM-DD — <short description>

- **Type**: violation | blind-spot | conflict | suggestion
- **Rule**: <which rule was involved>
- **Detail**: <what happened>
- **Resolution**: <what was done / what rule should be updated>
```

---

## Log Entries

### 2026-03-13 — Initial baseline established

- **Type**: suggestion
- **Rule**: N/A
- **Detail**: AI governance infrastructure created. `.ai/` directory with constitution, rules, checklists, and health tracking.
- **Resolution**: Baseline captured. Future drift will be measured against this point.

### 2026-03-14 — AI rule coverage blind spots in sync-heavy modules

- **Type**: blind-spot
- **Rule**: `CONSTITUTION.md` §3/§6, `CHANGE_PROTOCOL.md`
- **Detail**: The rule system covered kernel/primitives/api/tests well, but it
  lacked explicit guidance for domain services, transport modules outside REST,
  telemetry, large-file growth, and common sync-heavy changes such as offline
  jobs, provider adapters, and telemetry events.
- **Resolution**: Added global AI workflow constraints, expanded the routing
  table, added `domain-services.md`, `transport.md`, `telemetry.md`, and
  extended `CHANGE_PROTOCOL.md` with the missing synchronization maps.
