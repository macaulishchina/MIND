# Verification Policy

Use this policy to decide how much verification a change needs and how to
record the result.

## Principles

- Every non-small change must declare a verification profile.
- Verification must be explicit even when the repository has no automation.
- Profiles describe required depth; checks describe what evidence is needed.
- Missing automation is not a reason to skip verification. Record manual
  evidence and any limitations instead.

## Profile Selection

- Use `quick` for small, low-risk changes that still need a change folder.
- Use `feature` for behavior-changing feature work.
- Use `refactor` for internal restructuring with intended behavior parity.
- Use `full` before archiving any substantial change or when multiple risks
  stack together.

If unsure, choose the stronger profile.

## Required Outputs

Every non-small change should carry:

- a selected verification profile in `proposal.md`
- verification tasks in `tasks.md`
- a change-local verification report before archive

Suggested location:

```text
.ai/changes/<change-id>/verification-report.md
```

## Evidence Rules

- Automated command output is valid evidence when the repo has real commands.
- Manual review notes are valid evidence when no automation exists yet.
- Any skipped check must state why it was skipped and what substitute evidence
  was used.
- If `.ai/` changed, include the `human-doc-sync` check before archive.

## Archive Gate

Do not archive a change until its selected profile has been satisfied or its
remaining gaps are explicitly documented and accepted.
