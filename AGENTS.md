# Project Instructions

Read `.ai/README.md` first, then `.ai/project.md`, before making any non-small
change in this repository.

Workflow:

1. Use `.ai/project.md` to decide whether the request is a small change.
2. For any non-small change, create or continue a folder under
   `.ai/changes/<change-id>/`.
3. Draft `proposal.md` first.
4. Before moving toward implementation, challenge the requested direction
   against repo reality, conflicts, and feasibility.
5. Select a verification profile using `.ai/verification/policy.md`.
6. Add a change-local spec delta when behavior or acceptance criteria change.
7. Only after the proposal is approved, finalize `tasks.md` and implement.
8. Record verification results in `verification-report.md` before archive.
9. When the change is complete, merge approved spec updates into `.ai/specs/`
   and move the change folder into `.ai/archive/`.

If a change updates `.ai/`, review and update the relevant `.human/` handbook
documents whenever the change affects developer-facing guidance.

Use `.ai/templates/` and `.ai/verification/templates/` when creating new
workflow artifacts.
