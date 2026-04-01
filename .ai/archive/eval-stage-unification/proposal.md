# Change Proposal: Eval Stage Unification

## Metadata

- Change ID: `eval-stage-unification`
- Type: `feature`
- Status: `approved`
- Spec impact: `update required`
- Verification profile: `full`
- Owner: `Codex`
- Related specs: `owner-centered-add-eval`, `evaluation-workflow`

## Summary

- Refactor `tests/eval/` around one reusable case schema shared across multiple evaluation stages.
- Introduce a unified stage-oriented eval runner so owner-centered add and STL extraction evaluation use the same CLI shape.
- Reorganize pytest coverage so dataset shape, owner-add stage behavior, and STL stage behavior are tested separately and explicitly.

## Why Now

- The current case files already mix reusable input with multiple kinds of expectations, but only owner-centered add has a real evaluation contract; `eval_stl_extract.py` is an inspector, not a stage evaluator.
- The result is a half-shared topology: data is partly reusable, but test purpose is implicit and the command surface is fragmented.
- The user explicitly wants reusable datasets, clearer test purpose, multi-stage evaluation, and unified usage.

## In Scope

- Define one shared eval case format with common inputs plus stage-specific expectation sections.
- Add a unified eval runner entrypoint for stage-based execution.
- Rewrite existing case JSON files to the new schema without duplicating conversation inputs.
- Reorganize pytest coverage to match dataset/shared-runner/stage behavior.
- Update eval docs to describe the unified workflow and remove stale runner references.

## Out Of Scope

- Changing the runtime semantics of `Memory.add()` beyond what the eval stages already depend on.
- Reintroducing deprecated latency/speed runners.
- Creating a broad benchmark framework outside `tests/eval/`.

## Proposed Changes

- Case files will keep shared fields such as `id`, `description`, `owner`, and `turns`, and move expectations into explicit stage blocks such as `stages.owner_add` and `stages.stl_extract`.
- A new unified runner will accept `--stage owner_add|stl_extract` plus common dataset/case/report flags.
- Owner-add evaluation will read only `stages.owner_add` expectations; STL evaluation will read only `stages.stl_extract` expectations.
- `eval_stl_extract.py` will remain as a lightweight inspection tool, but stage-based pass/fail evaluation will move to the unified runner.
- Pytest coverage will be split into shared dataset tests, owner-add stage tests, and STL stage tests.

## Reality Check

- The current owner-centered runner already reuses refs/statements/evidence expectations, so moving to explicit stage blocks will change every case file and the current runner/test helper APIs together.
- A fully separate dataset per stage would avoid schema work, but it would duplicate conversation inputs and directly conflict with the reuse goal.
- Deleting the STL inspector would simplify entrypoints, but it would remove a useful debugging tool; keeping it as an inspector-only path is the narrower fit.
- Running all stages for every case by default would be convenient but could double model cost on real configs. The cleaner default is one unified runner with explicit `--stage` selection.

## Acceptance Signals

- One case file can be used by both owner-add and STL evaluation without duplicating its conversation input.
- The unified runner can execute either stage with the same case discovery and report conventions.
- Pytest coverage is grouped by dataset/shared behavior and by stage-specific behavior.
- README instructions describe one primary eval command shape and clearly distinguish evaluation from inspection.

## Verification Plan

- Profile: `full`
- Automated checks: focused pytest suites for shared dataset loader and both stages; manual CLI runs for `owner_add` and `stl_extract` against fake-backed config.
- Manual checks: review docs/specs for stale references to the deleted latency runner and the old fragmented eval usage.

## Open Questions

- None. The requested direction is explicit enough to implement directly.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
