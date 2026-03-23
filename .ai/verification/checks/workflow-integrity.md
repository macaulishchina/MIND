# Check: workflow-integrity

## Purpose

Verify that the change followed the repository's spec workflow correctly.

## When To Use

- every non-small change

## Pass Criteria

- The change has a valid `proposal.md`.
- The proposal status matches the actual stage of work.
- `tasks.md` was finalized only after proposal approval.
- The change folder contains all required artifacts for its declared impact.

## Acceptable Evidence

- artifact inspection
- reviewer confirmation
- future workflow linting if the repo adds it
