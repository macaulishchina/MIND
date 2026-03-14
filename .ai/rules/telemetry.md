# Rules: Telemetry (`mind/telemetry/`)

> Load this file when modifying telemetry contracts, runtime hooks, audits, or gates.

---

## Scope

Telemetry is the traceability layer for runtime behavior, audits, and gates.
Changes here affect observability quality as well as downstream evaluation.

## Rules

1. **Contract-first events**: Add or update event fields in
   `mind/telemetry/contracts.py` before emitting them from call sites. Avoid
   ad-hoc dict payloads.

2. **External-path changes need telemetry review**: When adding an endpoint,
   tool, command, provider path, or offline job, explicitly decide what event
   or trace should be emitted and where it is recorded.

3. **Update audits with schema changes**: If event ids or fields change, update
   `audit.py`, `audit_rules.py`, `gate.py`, and the corresponding tests in the
   same change.

4. **Prefer additive changes**: Add fields instead of renaming or removing them
   unless a coordinated migration is required.

5. **Keep debug data controlled**: Debug-only fields must satisfy the existing
   audit rules and must not leak into normal production flows by accident.

## Common Mistakes

- Adding a new event at a call site without updating telemetry contracts.
- Changing event shape without refreshing audit rules and phase-L tests.
- Recording raw debug payloads in production paths.
