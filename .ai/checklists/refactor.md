# Checklist: Refactoring

Use this checklist when refactoring existing code.

---

## Pre-work

- [ ] Define the refactoring goal in one sentence
- [ ] Confirm the refactoring is requested or clearly necessary (not "nice to have")
- [ ] Ensure the pre-commit full health check passes BEFORE starting (`uv run python scripts/ai_health_check.py --full --report-for-ai`)
- [ ] If the refactor spans more than 5 files, multiple subsystems, or more than one commit, create or update `PLANS.md` from `.ai/templates/PLANS.md`
- [ ] If the target file is over 400 lines, define the extraction boundary before editing

## Scope

- [ ] Change is limited to the stated goal — no feature additions
- [ ] No API/CLI/MCP interface changes (refactoring is internal)
- [ ] If interface changes are needed, that's a feature change, not a refactor

## Execution

- [ ] Make changes in small, verifiable steps
- [ ] Run tests after each step — never batch large changes
- [ ] Preserve all existing behavior (tests should pass without modification)
- [ ] If the target file is already over 500 lines, do not add a new
      responsibility without reducing file size or recording the debt in
      `.ai/health/drift-log.md`

## Testing

- [ ] All existing tests pass without modification
- [ ] If tests need updating, it's a signal the refactor changed behavior — verify intentional
- [ ] Add tests for any new internal abstraction that has complex logic

## Verification

- [ ] `uv run ruff check mind/ tests/` — zero errors
- [ ] `uv run mypy mind/ tests/` — zero errors
- [ ] `uv run python scripts/ai_health_check.py --report-for-ai` — quick local health check passes
- [ ] `uv run python scripts/ai_health_check.py --full --report-for-ai` — full health check passes
- [ ] No new files over 500 lines
- [ ] No new circular imports
- [ ] Architecture invariants still hold (see CONSTITUTION.md §2)
