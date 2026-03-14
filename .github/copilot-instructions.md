# MIND Project — Copilot Instructions

Before making any code change in this project, read `.ai/CONSTITUTION.md`.
It contains the project's architecture rules, coding standards, change
protocols, and a routing table for module-specific rules.

Key points:
- Layered architecture: Transport → App Services → Domain → Primitives → Kernel
- All app services use AppRequest/AppResponse envelope pattern
- All new services must be registered in AppServiceRegistry
- Type annotations required on all functions (mypy strict)
- Line length: 100 chars, Python 3.12+, Pydantic strict mode
- Follow CHANGE_PROTOCOL.md for file synchronization requirements

## Health Check

After completing code changes, run the health check:
```bash
uv run python scripts/ai_health_check.py --report-for-ai
```
Then read `.ai/health/repair-prompt.md` for a prioritized repair plan.
