# Fake Smoke Summary — decision-prompt-optimization

## Scope

- Direct A/B smoke:
  - `tests/eval/runners/eval_decision_ab.py`
  - config: `mindt.toml`
  - model: `fake:fake-memory-test`
  - cases: first 4 seed decision cases
- Offline optimizer smoke:
  - `tests/eval/decision_opt/optimize_decision_prompt.py`
  - config: `mindt.toml`
  - eval model: `fake:fake-memory-test`
  - cases: first 4 seed decision cases
  - rounds: `1`

## Result

- Direct A/B smoke wrote:
  - `decision_ab_fake_smoke_2026-04-02.json`
- Offline optimizer smoke wrote:
  - `fake_campaign_2026-04-02/baseline_report.json`
  - `fake_campaign_2026-04-02/round_01_candidate_prompt.txt`
  - `fake_campaign_2026-04-02/round_01_report.json`
  - `fake_campaign_2026-04-02/round_01_gate.json`
  - `fake_campaign_2026-04-02/campaign_summary.json`

## Interpretation

- These runs verify that the maintained dataset loader, A/B runner, scoring,
  promotion gate, and artifact-writing path all execute end-to-end.
- They do **not** count as prompt-quality evidence for production because the
  fake backend uses deterministic heuristics rather than a live development
  model.
- On the 4-case smoke slice, the fake backend still misses the `unrelated_add`
  case, which is expected fake-backend behavior rather than a claimed verdict
  on the new runtime prompt.
