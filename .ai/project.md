# Project Context

This file is the single long-lived entrypoint for project context.
Update it whenever the repository earns stable assumptions that future changes
should inherit.

## Current State

- This repository currently contains workflow scaffolding only.
- Product requirements, runtime architecture, and implementation stack are not
  yet defined in durable form.
- Until those details exist, do not invent fixed constraints that the repo has
  not committed to.

## Working Boundaries

- Keep changes scoped to the requested outcome.
- Prefer durable written context in repo files over chat-only decisions.
- Do not mix feature work, refactors, and unrelated cleanup in one change.
- Remove or update stale workflow instructions as soon as they are discovered.
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
- Treat proposal approval as the only hard gate before implementation.
- Create `design.md` only when technical decisions need a durable explanation.
- Use `.ai/verification/` to choose and satisfy a verification profile for each
  non-small change.
- When `.ai/` changes affect developer-facing workflow guidance, review and
  update the relevant `.human/` handbook sections before closing the change.

## Verification Model

- Verification is defined by policy, reusable profiles, reusable checks, and a
  change-local verification report.
- No repository-wide verification command is standardized yet.
- When the repo gains automation later, map concrete commands to the existing
  verification checks rather than replacing the model with a script path.

## Terminology

- `capability`: a coherent area of behavior described by one living spec
- `source of truth`: the approved current spec in `.ai/specs/`
- `change`: one proposed or active unit of work in `.ai/changes/`
- `proposal`: the document that explains why a change should happen
- `spec delta`: the proposed requirement changes stored inside a change folder
- `verification profile`: the required level of validation for a change
- `verification report`: the record of which checks were satisfied and how
- `human handbook`: the Chinese developer-facing documentation derived from
  `.ai/` and stored in `.human/`
- `archive`: completed changes kept for history after their specs are merged

## Add Later

When the project matures, extend this file with:

- project purpose and user outcomes
- real tech stack and repo layout
- architecture principles
- interface stability rules
- verification commands mapped onto the verification framework
- glossary entries tied to the product domain
