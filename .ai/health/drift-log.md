# AI Governance Drift Log

> Record rule violations, blind spots, and rule conflicts found during
> AI-driven development.

---

## Format

```text
### YYYY-MM-DD - <short description>

- **Type**: violation | blind-spot | conflict | suggestion
- **Rule**: <which rule was involved>
- **Detail**: <what happened>
- **Resolution**: <what was done or what should change>
```

---

## Log Entries

### 2026-03-23 - Reset to initial scaffold

- **Type**: suggestion
- **Rule**: N/A
- **Detail**: Removed repo-specific `.ai/` rules and stale state so the folder
  can act as a minimal spec-driven development scaffold.
- **Resolution**: Rebuild project-specific guidance incrementally only when the
  repo earns it.

### 2026-03-23 - Referenced health check entrypoint is missing

- **Type**: blind-spot
- **Rule**: Verification workflow
- **Detail**: The repository instructions referenced
  `scripts/ai_health_check.py`, but that path does not exist in the current
  repo snapshot.
- **Resolution**: Add the health check script later or simplify any repo
  instructions that still point to it.
