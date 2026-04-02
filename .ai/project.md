# Project Context

This file is the single long-lived entrypoint for project context.
Update it whenever the repository earns stable assumptions that future changes
should inherit.

## Current State

- This repository contains an implemented Python memory system plus the
  spec-driven workflow that governs ongoing changes.
- Durable project facts already exist in `.ai/specs/` for owner-centered
  memory, STL grammar/evaluation, and runtime logging behavior.
- The maintained regression baseline is the pytest suite under `tests/`; the
  repository also contains eval runners and prompt-optimization reports under
  `tests/eval/`.
- The maintained online STL extraction default currently uses the base STL
  prompt with a stage-specific extraction model profile rather than relying on
  the global LLM default accidentally.

## Working Boundaries

- Keep changes scoped to the requested outcome.
- Prefer durable written context in repo files over chat-only decisions.
- Do not mix feature work, refactors, and unrelated cleanup in one change.
- Do not write project-specific requirement drafts, planning notes, or ad hoc
  product direction into `.ai/` or `.human/` workflow docs unless they are
  being formalized as approved specs or change artifacts.
- Remove or update stale workflow instructions as soon as they are discovered.
- Do not blindly implement a requested direction when it is likely wrong,
  conflicting, or infeasible. Challenge it and recommend a better path.
- Treat `.human/` as the Chinese developer handbook derived from `.ai/`; when
  `.ai/` guidance changes, update the relevant `.human/` sections wherever the
  same guidance is meant for developers.

## Small Change Rule

A request counts as a small change only if all of the following are true:

- It affects one narrow behavior or one local wording/detail.
- It does not need approval beyond the immediate request.
- It does not change public behavior, interfaces, or acceptance criteria.
- It can be verified in one short step without a multi-file plan.

Anything else must use `.ai/changes/<change-id>/`.

## Workflow Defaults

- Use `.ai/specs/` for current truth only.
- Use `.ai/changes/` for proposed or active work only.
- Do not edit `.ai/specs/` as part of drafting; spec updates belong in the
  change folder until the change is accepted and ready to archive.
- Before approval, a proposal should contain a reality check when direction fit
  or feasibility is not obvious.
- Treat proposal approval as the only hard gate before implementation.
- Create `design.md` only when technical decisions need a durable explanation.
- Use `.ai/verification/` to choose and satisfy a verification profile for each
  non-small change.
- When `.ai/` changes affect developer-facing workflow guidance, review and
  update the relevant `.human/` handbook sections before closing the change.

## Verification Model

- Verification is defined by policy, reusable profiles, reusable checks, and a
  change-local verification report.
- The maintained automated regression command is `pytest tests/` (via the
  checked-in pytest config).
- Use targeted eval runners in `tests/eval/` when a change needs stage-level or
  prompt/model evidence in addition to the core pytest suite.
- Map concrete commands onto the existing verification checks rather than
  replacing the model with a script path.

## Terminology

- `capability`: a coherent area of behavior described by one living spec
- `source of truth`: the approved current spec in `.ai/specs/`
- `change`: one proposed or active unit of work in `.ai/changes/`
- `proposal`: the document that explains why a change should happen
- `reality check`: the part of a proposal that surfaces conflicts, infeasibility,
  fragile assumptions, and better alternatives before implementation
- `spec delta`: the proposed requirement changes stored inside a change folder
- `verification profile`: the required level of validation for a change
- `verification report`: the record of which checks were satisfied and how
- `human handbook`: the Chinese developer-facing documentation derived from
  `.ai/` and stored in `.human/`
- `archive`: completed changes kept for history after their specs are merged

## Add Later

When the project matures, extend this file with:

- project purpose and user outcomes
- architecture principles
- interface stability rules
- glossary entries tied to the product domain
