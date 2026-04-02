# Change Proposal: MVP Live Owner-Add Baseline

## Metadata

- Change ID: `mvp-live-eval-baseline`
- Type: `feature`
- Status: `archived`
- Spec impact: `update required`
- Verification profile: `full`
- Owner: `agent`
- Related specs: `mvp-release-readiness`, `owner-centered-add-eval`, `evaluation-workflow`

## Summary

- Produce the first durable MVP baseline for the real `owner_add` pipeline by
  running the maintained unified eval runner against the real-model
  `mind.toml` configuration and recording the result as point-in-time evidence.

## Why Now

- `mvp-closeout` established docs, smoke coverage, and MVP acceptance
  boundaries, but it intentionally stopped short of recording live real-model
  owner-add evidence.
- The repository now has a maintained STL extraction runtime default, so the
  MVP needs one matching owner-add baseline before post-MVP quality work
  resumes.
- Without a recorded baseline, later v1.5 work will lack a clear "before"
  reference for real-model behavior.

## In Scope

- Run the unified `owner_add` eval stage against the maintained real-model
  config in `mind.toml`.
- Save a tracked report artifact and a concise human-readable baseline summary.
- Document how to reproduce the live baseline and how to interpret it.
- Extend the MVP release-readiness spec so the live baseline is treated as
  archived evidence, not as a deterministic CI gate.

## Out Of Scope

- STL prompt optimization or new prompt experiments.
- Changing runtime defaults or model-selection policy.
- Relaxing owner-add metric targets to fit the first live run.
- Turning live real-model eval into a required per-change automated gate.

## Proposed Changes

### 1. Create a durable live baseline artifact

- Run `tests/eval/runners/eval_cases.py --stage owner_add --toml mind.toml`
  across the maintained case set.
- Save the JSON report under `tests/eval/reports/` and add a concise summary
  that captures the command, runtime context, metric outcomes, and failed
  cases.

### 2. Document reproduction and interpretation

- Update MVP-facing evaluation docs to point to the maintained live-baseline
  command and report path.
- Make it explicit that this live baseline is informative point-in-time
  evidence, while deterministic day-to-day regression remains `pytest tests/`.

### 3. Promote the baseline into MVP readiness expectations

- Update the MVP release-readiness spec so the repository is expected to carry
  one archived live owner-add baseline with enough context for future
  comparison.

## Reality Check

- Real-model eval is inherently nondeterministic and depends on local secrets,
  network health, and the untracked `mind.toml` runtime environment. That makes
  it unsuitable as a hard CI requirement or a promise that every machine will
  reproduce identical numbers.
- Because `mind.toml` is gitignored, the repo can only document the maintained
  config shape and baseline command, not the user's exact secret-bearing local
  configuration.
- The current owner-add targets are intentionally strict. If the live run misses
  them, the correct first move is to record the actual baseline and residual
  risk, not quietly redefine success.
- The narrower repo-realistic direction is to record and explain the current
  behavior. Expanding datasets, rewriting prompts, or changing runtime defaults
  would turn this into a larger quality campaign rather than an MVP baseline.

## Acceptance Signals

- A real `owner_add` eval run against `mind.toml` is recorded in a tracked
  report artifact.
- The repository documents the reproduction command, output location, and the
  distinction between live evidence and deterministic regression.
- `mvp-release-readiness` includes the approved live-baseline expectation.
- The verification report records the live run outcome, any metric misses, and
  residual risk clearly enough to compare against future changes.

## Verification Plan

- Profile: `full`
- Automated evidence:
  - Run the live owner-add eval with `mind.toml`
  - Run `.venv/bin/python -m pytest tests/`
- Manual evidence:
  - Review updated MVP docs/specs for alignment with the recorded report
  - Review `.human/` handbook impact because `.ai/` source-of-truth files will
    change
- Required checks: `workflow-integrity`, `change-completeness`,
  `spec-consistency`, `manual-review`, `human-doc-sync`,
  `automated-regression`, `live-baseline-evidence`

## Open Questions

- None blocking. If the first live baseline misses current targets, this change
  will document the miss and carry it forward as baseline evidence rather than
  expand into a new optimization scope.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
