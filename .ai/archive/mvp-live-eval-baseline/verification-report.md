# Verification Report: mvp-live-eval-baseline

## Metadata

- Change ID: `mvp-live-eval-baseline`
- Verification profile: `full`
- Status: `complete`
- Prepared by: `agent`

## Checks Run

### `workflow-integrity`

- Result: `pass`
- Evidence:
  - Proposal created and approved in
    `.ai/archive/mvp-live-eval-baseline/proposal.md`
  - Change-local spec delta created for `mvp-release-readiness`
  - Tasks, artifacts, and this verification report were added before archive
- Notes:
  - The change stayed scoped to MVP live baseline evidence and did not expand
    into STL optimization or runtime-default changes

### `change-completeness`

- Result: `pass`
- Evidence:
  - Added tracked live-baseline artifacts:
    - `.ai/archive/mvp-live-eval-baseline/artifacts/owner_add_live_baseline_2026-04-02.json`
    - `.ai/archive/mvp-live-eval-baseline/artifacts/owner_add_live_baseline_2026-04-02.md`
  - Updated MVP-facing docs:
    - `README.md`
    - `Doc/core/评测方案.md`
    - `tests/eval/README.md`
  - Updated living spec:
    - `.ai/specs/mvp-release-readiness/spec.md`
  - Synced handbook context:
    - `.human/context.md`
    - `.human/verification.md`
- Notes:
  - The ignored `tests/eval/reports/` output was copied into tracked change
    artifacts so the baseline survives archive

## Additional Checks

### `spec-consistency`

- Result: `pass`
- Evidence:
  - Change-local delta:
    `.ai/archive/mvp-live-eval-baseline/specs/mvp-release-readiness/spec.md`
  - Living spec now includes the approved requirement that MVP carries a live
    owner-add baseline as archived evidence, not as a deterministic CI gate
  - README and eval docs now use the same distinction between:
    - day-to-day regression: `pytest tests/`
    - point-in-time live evidence: `eval_cases.py --stage owner_add --toml mind.toml`
- Notes:
  - No conflicts were found between the new MVP baseline requirement and the
    existing owner-centered eval or evaluation-workflow specs

### `human-doc-sync`

- Result: `pass`
- Evidence:
  - `.human/verification.md` now explains that live real-model baselines are
    point-in-time evidence rather than default gates
  - `.human/context.md` now notes that the MVP keeps one archived live
    `owner_add` baseline alongside deterministic daily regression
- Notes:
  - This sync was required because `.ai/specs/` changed the maintained MVP
    readiness expectations

### `automated-regression`

- Result: `pass`
- Evidence:
  - `.venv/bin/python -m pytest tests/`
    - `194 passed in 10.09s`
- Notes:
  - No code behavior changed in this change, but full-suite regression was kept
    as the deterministic baseline required by the proposal

### `live-baseline-evidence`

- Result: `pass`
- Evidence:
  - `.venv/bin/python tests/eval/runners/eval_cases.py --stage owner_add --toml mind.toml --pretty --output tests/eval/reports/mvp_live_owner_add_baseline_2026-04-02.json`
  - Report summary:
    - total cases: `14`
    - default model: `leihuo/qwen3.5-flash`
    - stage model: `leihuo/gpt-5.4-mini`
    - `canonical_text_accuracy = 0.667`
    - `subject_ref_accuracy = 0.667`
    - `count_accuracy = 0.714`
    - `owner_accuracy = 1.000`
    - `case_pass_rate = 0.643`
  - Failed cases recorded in the report artifacts:
    - `owner-add-001`
    - `owner-add-004`
    - `owner-add-005`
    - `owner-comprehensive-001`
    - `owner-rel-owner-002`
- Notes:
  - The live baseline intentionally records the actual outcome even though
    several metrics missed their configured targets

### `manual-review`

- Result: `pass`
- Evidence:
  - Reviewed the baseline summary against the raw JSON report to ensure the
    documented failure patterns match the recorded active memories
  - Reviewed README, `Doc/core/评测方案.md`, and `tests/eval/README.md` to
    ensure they do not present live eval as a deterministic per-change gate
  - Reviewed `.human/` sync impact after the living spec update
- Notes:
  - The main nuance preserved in docs is that the baseline reflects the current
    runtime split: STL extraction override plus the global decision-stage model

## Residual Risk

- The baseline is a single point-in-time run against local `mind.toml`, so
  future reruns may vary because of provider behavior, credentials, or network
  conditions
- Several owner-add metrics are materially below target; this change records
  that fact but does not attempt to remediate it
- The raw runner output path under `tests/eval/reports/` remains ignored by
  git; the tracked archive copy is now the durable source for this baseline

## Summary

- The selected `full` profile is satisfied
- No verification gaps are being accepted beyond the explicitly documented
  nondeterminism of live real-model evaluation
