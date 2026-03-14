# MIND Project Instructions

Read `.ai/CONSTITUTION.md` before making any code changes.
This is the project's AI governance file containing architecture rules,
coding standards, change protocols, and rule routing tables.

For module-specific rules, follow the routing table in CONSTITUTION.md §6.
For change-type checklists, follow the routing table in CONSTITUTION.md §7.

## Health Check

After completing code changes, run the health check:
```bash
uv run python scripts/ai_health_check.py --report-for-ai
```
Then read `.ai/health/repair-prompt.md` for a prioritized repair plan.

Also run this when the user requests a health assessment, full check,
AI health test, or similar (e.g. "做全面检查", "健康检测", "跑一下测试").
