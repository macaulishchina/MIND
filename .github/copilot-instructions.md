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

Also run this when the user requests a health assessment, full check,
AI health test, or similar (e.g. "做全面检查", "健康检测", "跑一下测试").
For routine pytest runs, prefer the parallel quick command from `.ai/rules/testing.md`
instead of bare `uv run pytest tests/`.
