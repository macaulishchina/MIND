# Change Proposal: Close out STL optimization and formalize runtime defaults

## Metadata

- Change ID: `stl-runtime-closeout`
- Type: `feature`
- Status: `archived`
- Spec impact: `update required`
- Verification profile: `full`
- Owner: `agent`
- Related specs: `runtime-llm-strategy`

## Summary

- Update stale project/workflow docs to reflect the repository's actual
  maturity.
- Close out completed active change folders that were left under
  `.ai/changes/`.
- Formalize the current default STL extraction runtime strategy in config and
  docs based on the completed prompt optimization campaign.

## Why Now

- `.ai/project.md` still describes the repository as workflow scaffolding only,
  which conflicts with the current codebase, specs, eval framework, and tests.
- Several completed changes still appear active, which makes the workflow state
  noisy and misleading.
- The prompt optimization campaign already produced a concrete runtime
  recommendation, but the maintained default config has not absorbed it yet.

## In Scope

- Update long-lived workflow/project context in `.ai/` and matching `.human/`
  handbook files.
- Archive completed change folders that no longer belong in `.ai/changes/`.
- Add a durable spec for the default online STL extraction runtime profile.
- Update config/code/docs so the default STL extraction stage uses the selected
  model/profile and timeout policy.
- Add targeted tests for the new config resolution behavior.

## Out Of Scope

- Further STL prompt rewriting or new prompt experiments.
- Changing the owner-centered decision stage default model.
- Re-running the full prompt optimization campaign.
- Large feature work from the v1.5/v2 roadmap.

## Proposed Changes

### 1. Align long-lived context with repo reality

- Rewrite `.ai/project.md` so it describes the repository as an implemented
  memory system with active specs, tests, and eval tooling rather than workflow
  scaffolding only.
- Update the corresponding `.human/` handbook pages so the Chinese developer
  guidance stays semantically aligned.

### 2. Archive completed active changes

- Move completed change folders that no longer represent active work from
  `.ai/changes/` into `.ai/archive/`.
- Preserve their existing artifacts rather than retroactively inventing new
  historical documents for already-finished work.

### 3. Formalize the default STL extraction runtime profile

- Add a durable spec stating that the maintained online STL extraction default
  uses the base STL prompt, a stage-specific extraction model, and a bounded
  request timeout.
- Extend stage override config resolution so a stage can carry its own normal
  request timeout, not just batch timeout.
- Update `mind.toml` and README guidance so the maintained default STL
  extraction stage uses `leihuo:gpt-5.4-mini`, keeps
  `stl_extraction_supplement = false`, and applies a 10s timeout budget.

## Reality Check

- The prompt optimization report does **not** prove that `gpt-5.4-mini` is the
  highest-quality extraction model; it proves that it is the best current
  production default under latency and reliability constraints. The default
  strategy should therefore be scoped to the STL extraction stage only.
- The report's 10s timeout was enforced by the eval runner, not by maintained
  runtime config. If we want that policy to be durable, config resolution must
  expose normal request timeout control first.
- Some completed active change folders have incomplete historical artifacts
  (for example, `stl-golden-expected` lacks a proposal). Reconstructing missing
  history now would create synthetic provenance; archiving the existing folder
  as-is is the safer direction.
- README currently mixes current and superseded STL concepts (`evidence` is
  still named in the main add-flow summary). Closing this gap is necessary for
  consistency, but we should avoid broad documentation rewrites outside the
  STL/runtime scope.

## Acceptance Signals

- `.ai/project.md` and the synced `.human/` handbook describe the actual repo
  state rather than scaffold-only status.
- Completed change folders no longer appear under `.ai/changes/`.
- A living spec exists for the maintained STL extraction runtime strategy.
- `mind.toml` resolves a stage-specific STL extraction default matching the
  chosen runtime profile.
- Tests cover stage-specific timeout resolution and continue to pass.

## Verification Plan

- Profile: `full`
- Checks: `workflow-integrity`, `change-completeness`, `spec-consistency`,
  `human-doc-sync`, and targeted automated test evidence.
- Run focused pytest coverage for config resolution and existing batch/stage
  override behavior.
- Record manual review evidence for doc alignment and archive state cleanup.

## Open Questions

- None blocking. This change intentionally keeps the decision stage on existing
  defaults and treats only STL extraction as productionized from the prompt
  campaign.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
