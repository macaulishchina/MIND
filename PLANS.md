# Execution Plan

## Goal

- Reduce `.ai/` to a minimal, reusable spec-driven development scaffold.

## Why Now

- The current `.ai/` contents are heavily tailored to an older project shape.
- We want a clean starting point before adding new rules or project-specific details.

## Constraints

- Prefer deleting or neutralizing existing customization over adding new structure.
- Keep the scaffold usable for future expansion.
- Avoid changing files outside `.ai/` unless a consistency issue forces it.

## Non-Goals

- Defining a full architecture, tooling stack, or workflow.
- Replacing deleted detail with new project-specific guidance.
- Adding new rule packs beyond the minimum scaffold.

## Affected Areas

- `.ai/CONSTITUTION.md`
- `.ai/ARCHITECTURE.md`
- `.ai/CHANGE_PROTOCOL.md`
- `.ai/CONVENTIONS.md`
- `.ai/CURRENT_STATE.md`
- `.ai/checklists/`
- `.ai/rules/`
- `.ai/health/drift-log.md`

## Risks

- Removing too much could leave the scaffold confusing.
- Leaving stale references behind would defeat the cleanup.

## Steps

1. Rewrite retained top-level `.ai` files into generic, initial-scaffold placeholders.
2. Rewrite the generic checklists we want to keep.
3. Delete clearly project-specific rules and checklists.
4. Search `.ai/` for stale project-specific references and fix anything left.

## Verification

- Confirm the resulting `.ai/` tree only contains generic scaffold files.
- Search `.ai/` for stale project-specific terms and paths.
- Note any verification steps that cannot run because the repo does not contain the referenced tooling.
- Attempt the quick health check once and record the result.

## Progress Log

- `done` Created plan for `.ai/` scaffold cleanup.
- `done` Rewrote retained `.ai/` files into generic scaffold placeholders.
- `done` Deleted project-specific rules and checklist files.
- `done` Verified that `.ai/` no longer contains stale project-specific paths or toolchain references.
- `done` Attempted `uv run python scripts/ai_health_check.py --report-for-ai`; the repo does not contain `scripts/ai_health_check.py`.

## Decisions

- Keep the existing `.ai/` folder structure where it still helps orientation.
- Prefer empty placeholders over speculative new rules.
- Keep only generic top-level governance files, two generic checklists, the drift log, and the plan template.

## Open Questions

- Whether to add a standardized `proposal/spec/design/tasks` layout later.
- Whether root-level instructions outside `.ai/` should also be reduced to match the new scaffold.
