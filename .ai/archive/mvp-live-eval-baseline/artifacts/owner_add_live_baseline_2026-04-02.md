# MVP Live Owner-Add Baseline (2026-04-02)

## Purpose

- Record the first point-in-time MVP baseline for the real `Memory.add()`
  owner-add pipeline using the maintained `mind.toml` runtime path.
- Keep this as comparison evidence for future v1.5 quality work without
  turning it into a deterministic per-change gate.

## Command

```bash
.venv/bin/python tests/eval/runners/eval_cases.py \
  --stage owner_add \
  --toml mind.toml \
  --pretty \
  --output tests/eval/reports/mvp_live_owner_add_baseline_2026-04-02.json
```

## Runtime Context

- Config: `mind.toml`
- Dataset: `tests/eval/cases/`
- Cases evaluated: `14`
- Default model: `leihuo/qwen3.5-flash`
- STL extraction stage model: `leihuo/gpt-5.4-mini`

## Metrics

- `canonical_text_accuracy`: `0.667` (target `0.95`)
- `subject_ref_accuracy`: `0.667` (target `0.95`)
- `count_accuracy`: `0.714` (target `0.95`)
- `owner_accuracy`: `1.000` (target `1.00`)
- `case_pass_rate`: `0.643` (target `0.95`)

## Failed Cases

### `owner-add-001`

- Expected self facts were projected as named-person subjects
  (`[person:john] ...`) instead of `[self] ...`.

### `owner-add-004`

- The unnamed third-party placeholder case produced no active memories.

### `owner-add-005`

- The correction case kept the final name memory, but also projected an extra
  `[self] attribute:correct_intent=$3` memory.

### `owner-comprehensive-001`

- The multi-turn Chinese comprehensive case produced empty STL output and no
  active memories.

### `owner-rel-owner-002`

- The coworker habit case projected relation + drink memories, but leaked the
  temporal modifier into an extra `[self] attribute:time=every morning`
  memory and missed the expected combined habit phrasing.

## Interpretation

- This baseline is useful evidence because it shows the current online owner-add
  path is strong on owner attribution (`owner_accuracy = 1.0`) but still weak
  on self anchoring, correction projection, complex multi-turn Chinese cases,
  and modifier attachment.
- The result reflects the maintained MVP runtime split:
  - STL extraction uses `gpt-5.4-mini`
  - post-extraction decision behavior still follows the global default model
- Deterministic day-to-day regression remains `pytest tests/`; this live
  baseline should be rerun intentionally when the maintained runtime strategy
  or owner-add behavior changes.

## Artifacts

- Raw JSON report:
  [owner_add_live_baseline_2026-04-02.json](/home/huyidong/workspace/MIND/.ai/archive/mvp-live-eval-baseline/artifacts/owner_add_live_baseline_2026-04-02.json)
