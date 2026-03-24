# Spec Workflow Workspace

This `.ai/` directory is the repository's spec-driven workflow workspace.
Start here before planning or implementing any non-small change.

`.human/` is the Chinese developer handbook for this workflow. It is organized
for human reading and must stay semantically aligned with `.ai/` whenever
developer-facing guidance changes.

Do not use `.ai/` or `.human/` as a catch-all location for project planning
notes, product ideas, or requirement drafts. Keep project-specific materials
outside these workflow docs unless they are being captured as approved living
specs or change-local workflow artifacts.

## Reading Order

1. Read `.ai/README.md`.
2. Read `.ai/project.md`.
3. Read `.ai/verification/policy.md` for any non-small change.
4. Read the relevant capability spec in `.ai/specs/` if one exists.
5. If the work already has a change folder, continue in `.ai/changes/<change-id>/`.
6. If the work is not a small change and no change folder exists, create one
   under `.ai/changes/<change-id>/` using the templates in `.ai/templates/`.

## Folder Map

- `.ai/project.md`: long-lived project context
- `.ai/specs/`: current approved source of truth
- `.ai/changes/`: active or proposed changes
- `.ai/archive/`: completed changes preserved for traceability
- `.ai/verification/`: verification policy, profiles, checks, and report template
- `.ai/templates/`: copyable templates for new workflow artifacts
- `.human/`: Chinese developer handbook derived from the `.ai/` workflow

## Standard Workflow

1. Decide whether the request is a small change using `.ai/project.md`.
2. For any non-small change, create `.ai/changes/<change-id>/proposal.md`.
3. Add a change-local spec delta when behavior, contracts, or acceptance
   criteria change.
4. Challenge the requested direction against existing facts, constraints,
   feasibility, and better alternatives.
5. Clarify the proposal until it can be explicitly approved.
6. Select a verification profile using `.ai/verification/policy.md`.
7. Only after approval, finalize `tasks.md` and begin implementation.
8. Complete the selected verification profile and record the result.
9. When implementation is complete, merge accepted spec changes into
   `.ai/specs/`.
10. If the change modified `.ai/` workflow guidance, update the relevant
   `.human/` handbook documents as needed.
11. Move the completed change folder into `.ai/archive/`.

## Artifact Rules

- `proposal.md` is required for every non-small change.
- `tasks.md` is required before implementation begins.
- `verification-report.md` is required before archive for every non-small change.
- `design.md` is optional and should only exist when technical decisions need
  durable explanation.
- A change-local `spec.md` is required when behavior, interfaces, validation,
  or acceptance criteria change.
- A refactor or bugfix with no spec impact must state `Spec impact: none` in
  `proposal.md`.
- A non-small change proposal must record its reality check: likely conflicts,
  infeasibility, wrong assumptions, or better alternatives when relevant.
- A change that updates `.ai/` developer-facing guidance must review the
  relevant `.human/` handbook coverage before archive.

## Approval Gate

Proposal approval is the only hard gate before implementation.
Clarification is a phase, not a required standalone file.
A proposal should not be approved until important feasibility concerns and
directional conflicts have been surfaced.

## Archive Rule

Do not treat `.ai/changes/` as permanent history.
Once a change is implemented and its approved spec updates are merged into
`.ai/specs/`, move the entire change folder into `.ai/archive/`.
