# Execution Plan

## Goal

- Replace the `.human/` mirror tree with a Chinese, developer-friendly handbook
  that remains semantically aligned with `.ai/` without mirroring its layout.

## Why Now

- The current `.human/` tree is a structural copy of `.ai/`, which is not the
  intended experience for human readers.
- Developers need a smaller set of Chinese documents organized by reading task,
  while `.ai/` remains the operational workflow source.

## Constraints

- `.human/` must still cover the full developer-relevant meaning of `.ai/`.
- `.human/` should be organized for human reading, not file-by-file parity.
- `.ai/` must explicitly state that `.human/` is semantically aligned, not mirrored.

## Non-Goals

- Changing the core `.ai/` workflow structure.
- Adding scripts to generate `.human/` automatically.
- Introducing human-only rules that diverge from `.ai/`.

## Affected Areas

- `AGENTS.md`
- `.ai/README.md`
- `.ai/project.md`
- `.ai/changes/README.md`
- `.ai/templates/tasks.md`
- `.ai/verification/policy.md`
- `.ai/verification/checks/human-doc-sync.md`
- `.ai/verification/checks/change-completeness.md`
- `.human/`

## Risks

- If `.human/` is too condensed, it may miss important `.ai/` semantics.
- If `.ai/` still uses mirror language, future updates will recreate the wrong expectation.

## Steps

1. Replace mirror-oriented wording in `.ai/` and root instructions with
   semantic-alignment wording.
2. Rebuild `.human/` as a compact Chinese handbook organized by reader tasks.
3. Verify that `.human/` still covers the developer-facing meaning of `.ai/`.

## Verification

- Inspect the new `.human/` file set and confirm it is task-oriented, not mirrored.
- Spot-check `.ai/` for updated wording about `.human/`.
- Search for stale `mirror` wording and remove it where inaccurate.

## Progress Log

- `done` Confirmed the old `.human/` tree was a mirror structure.
- `done` Removed the old `.human/` tree.
- `done` Rewrote `.ai/` sync rules to require semantic alignment instead of mirroring.
- `done` Created the new Chinese developer handbook under `.human/`.
- `done` Verified semantic coverage and removed stale mirror wording outside the plan record.

## Decisions

- `.ai/` remains the workflow source of truth.
- `.human/` becomes a Chinese developer handbook derived from `.ai/`.
- Alignment is semantic coverage, not one-file-to-one-file mapping.

## Open Questions

- Whether future tooling should help track semantic coverage between `.ai/` and `.human/`.
