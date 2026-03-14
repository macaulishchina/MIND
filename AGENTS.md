# MIND Project Instructions

Read `.ai/CONSTITUTION.md` before making any code changes.
This is the project's AI governance file containing architecture rules,
coding standards, change protocols, and rule routing tables.

For module-specific rules, follow the routing table in CONSTITUTION.md §6.
For change-type checklists, follow the routing table in CONSTITUTION.md §7.

For any large or multi-step change, create or update a repo-root `PLANS.md`
from `.ai/templates/PLANS.md` before editing code.

## Health Check

Use one health-check mode per verification milestone.
For local iteration, run the quick health check:
```bash
uv run python scripts/ai_health_check.py --report-for-ai
```
For final verification or before committing, run the full health check instead:
```bash
uv run python scripts/ai_health_check.py --full --report-for-ai
```
The full check subsumes the quick check, so do not run both back-to-back for the same verification step.
Then read `.ai/health/repair-prompt.md` for a prioritized repair plan.
