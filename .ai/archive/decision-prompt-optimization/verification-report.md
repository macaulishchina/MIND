# Verification Report: decision-prompt-optimization

## Metadata

- Change ID: `decision-prompt-optimization`
- Verification profile: `full`
- Status: `complete`
- Prepared by: `Codex`

## Checks Run

### `workflow-integrity`

- Result: `pass`
- Evidence:
  - Proposal created and approved in
    `.ai/archive/decision-prompt-optimization/proposal.md`
  - Change-local spec delta added in
    `.ai/archive/decision-prompt-optimization/specs/evaluation-workflow/spec.md`
  - Tasks finalized before implementation in
    `.ai/archive/decision-prompt-optimization/tasks.md`
- Notes:
  - The change stayed scoped to decision-prompt evaluation, offline optimization,
    and the runtime prompt update itself.

### `change-completeness`

- Result: `pass`
- Evidence:
  - Added the maintained decision dataset under
    `tests/eval/decision_opt/cases/`
  - Added shared decision eval / optimizer helpers under
    `tests/eval/decision_opt/`
  - Added the maintained direct A/B runner
    `tests/eval/runners/eval_decision_ab.py`
  - Strengthened the runtime prompt in `mind/prompts.py`
  - Added pytest coverage in `tests/test_decision_prompt_opt.py`
  - Added tracked smoke artifacts under
    `.ai/archive/decision-prompt-optimization/artifacts/`
- Notes:
  - The implementation now covers dataset, scoring, runner, offline optimizer,
    runtime prompt text, docs, and workflow artifacts together.

## Additional Checks

### `spec-consistency`

- Result: `pass`
- Evidence:
  - Merged approved requirements into `.ai/specs/evaluation-workflow/spec.md`
  - `tests/eval/README.md` now documents the same dedicated decision workflow
    and offline-gated optimization model as the living spec
- Notes:
  - The new spec language explicitly keeps self-optimization offline and gated,
    which matches the implemented optimizer behavior.

### `automated-regression`

- Result: `pass`
- Evidence:
  - `.venv/bin/python -m pytest tests/test_decision_prompt_opt.py tests/test_fake_llm.py -q`
    -> `11 passed`
  - `.venv/bin/python -m pytest tests/`
    -> `217 passed in 5.65s`
  - `.venv/bin/python -m py_compile tests/eval/decision_opt/core.py tests/eval/decision_opt/judge.py tests/eval/decision_opt/ab.py tests/eval/decision_opt/optimizer.py tests/eval/decision_opt/optimize_decision_prompt.py tests/eval/runners/eval_decision_ab.py mind/llms/fake.py tests/test_decision_prompt_opt.py`
    -> success
- Notes:
  - The targeted run covered the new decision dataset, scoring, gating, and
    fake prompt-shape behavior before the full suite was executed.

### `decision-tooling-smoke`

- Result: `pass`
- Evidence:
  - Direct runner smoke:
    - `.venv/bin/python tests/eval/runners/eval_decision_ab.py --toml mindt.toml --model fake:fake-memory-test --case tests/eval/decision_opt/cases --limit 4 --output .ai/archive/decision-prompt-optimization/artifacts/decision_ab_fake_smoke_2026-04-02.json --pretty`
  - Offline optimizer smoke:
    - `.venv/bin/python tests/eval/decision_opt/optimize_decision_prompt.py --toml mindt.toml --eval-model fake:fake-memory-test --case tests/eval/decision_opt/cases --limit 4 --rounds 1 --artifacts-dir .ai/archive/decision-prompt-optimization/artifacts/fake_campaign_2026-04-02`
  - Summary note:
    - `.ai/archive/decision-prompt-optimization/artifacts/fake_smoke_summary_2026-04-02.md`
- Notes:
  - These smokes verify the maintained CLI paths, report writing, candidate
    prompt generation, and promotion gate execution end-to-end.
  - They are intentionally recorded as tooling evidence, not production-quality
    prompt evidence.

### `human-doc-sync`

- Result: `pass`
- Evidence:
  - Updated `.human/context.md`
  - Updated `.human/verification.md`
- Notes:
  - The handbook now explains that decision prompt work should prefer the
    direct decision harness over only reading `owner_add` end-to-end results.

## Residual Risk

- No live development-model campaign was run in this environment, so the change
  does not yet include quantitative evidence that the new runtime prompt beats
  the previous prompt on real model behavior.
- The first seed dataset is intentionally narrow and anchored to the current
  runtime decision path. It improves observability now, but it is not yet a
  broad coverage set for every future decision-style memory scenario.
- The fake backend is deterministic and useful for tooling verification, but it
  is not a reliable proxy for prompt quality. A future real-model campaign
  should still be archived separately if the team wants promotion evidence.

## Summary

- The selected `full` profile is satisfied.
- Dataset, runner, offline optimizer, runtime prompt update, docs, and
  handbook sync were all implemented and verified.
