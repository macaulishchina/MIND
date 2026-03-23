# Verification Profile: Refactor

Use this profile for internal changes that intend to preserve behavior.

## Required Checks

- `workflow-integrity`
- `change-completeness`
- `behavior-parity`
- `manual-review`

## Typical Use

- code movement or decomposition
- dependency cleanup
- implementation simplification without intended spec change

## Success Standard

The change is well-scoped, the intended behavior remains intact, and any
residual risk is explicitly documented.
