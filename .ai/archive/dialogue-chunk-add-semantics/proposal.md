# Change Proposal: Dialogue-Chunk Add Semantics

## Metadata

- Change ID: `dialogue-chunk-add-semantics`
- Type: `feature`
- Status: `archived`
- Spec impact: `update required`
- Verification profile: `full`
- Owner: `Codex`
- Related specs: `owner-centered-memory`, `owner-centered-add-eval`

## Summary

- Redefine `Memory.add()` as a dialogue-chunk submission API: one call handles one newly submitted batch of messages, regardless of how many turns that batch contains.
- Redefine owner-centered add evaluation to execute each case with a single `Memory.add()` call after flattening the case `turns` into one ordered message list.
- Remove owner-centered add evaluation expectations and metrics that depend on cross-submission update/version/delete behavior.

## Why Now

- The current runtime and eval semantics treat case `turns` as repeated `Memory.add()` calls, which leaks authoring structure into business behavior.
- The requested business model is chunk-based: the caller decides when to submit a new conversation chunk, and the memory layer should not care how many turns exist inside that chunk.
- The current owner-centered eval surface reinforces the old model through specs, docs, metrics, and cases, so the repo needs one coherent truth instead of split semantics.

## In Scope

- Rewrite `Memory.add()` docs and runtime handling around chunk-level submission.
- Prevent batch-internal corrections from surfacing as final owner memories.
- Rewrite owner-centered add runner, report metrics, tests, and docs to single-submit semantics.
- Update the living specs and archive the approved change once verification is recorded.

## Out Of Scope

- Preserving backward-compatible eval semantics.
- Introducing a second public add API.
- Redesigning unrelated STL parser or storage capabilities beyond what is required to enforce chunk-level final-state projection.

## Proposed Changes

- Keep `Memory.add(messages=..., owner=..., session_id=..., metadata=...)` as the public entrypoint, but define it as one chunk submission rather than a per-turn operation.
- Persist STL for the submitted chunk once, then project only statements that remain current after the chunk's own correction handling.
- Keep case `turns` as authoring structure only; flatten them before the single runtime call.
- Remove update/version/delete assertions and metrics from owner-centered add eval.

## Reality Check

- Current specs, runner docs, tests, and representative cases explicitly say that the runner applies case turns in order through repeated `Memory.add()` calls; all of those statements become wrong under the new contract and must be rewritten together.
- The existing STL store correction flow already marks superseded statements, but owner-memory projection currently ignores that current/non-current distinction and therefore still emits batch-internal intermediate memories.
- Some runtime tests legitimately cover cross-submission version tracking; those tests should remain in runtime coverage, but they should no longer define owner-centered add eval semantics.
- Keeping both old and new case semantics would add confusion and maintenance noise. The narrower and cleaner direction is a full replacement.

## Acceptance Signals

- `Memory.add()` processes a multi-message chunk with one STL extraction pass and projects only final current statements from that chunk.
- Owner-centered add eval executes multi-turn cases with one `Memory.add()` call and produces reports without update/version metrics.
- Repo docs and living specs describe only the chunk-level contract.
- Regression coverage still protects cross-submission update/version behavior outside the owner-centered add eval surface.

## Verification Plan

- Profile: `full`
- Automated checks: focused pytest coverage for runtime + eval runner; owner-centered eval CLI run against fake-backed test config.
- Manual checks: grep-level review of specs/docs for stale per-turn semantics; review of `.ai/` artifacts and archive state.

## Open Questions

- None. The requested direction and scope are explicit.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
