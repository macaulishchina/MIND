# Change Proposal: Audit And Repair LLM Stage Configuration

## Metadata

- Change ID: `llm-stage-config-audit`
- Type: `bugfix`
- Status: `archived`
- Spec impact: `update required`
- Verification profile: `full`
- Owner: `Codex`
- Related specs: `owner-centered-memory`

## Summary

- Audit every LLM stage configuration surface, classify which stages are on the current `Memory.add()` path versus legacy helper paths, and repair the code/config/docs so the default TOML files only advertise meaningful runtime knobs.

## Why Now

- `mind.toml` and `mindt.toml` currently surface four stage blocks as if they were equally relevant, but the runtime paths are no longer symmetrical.
- `llm.stl_extraction` and `llm.decision` are active on the current STL-native `add()` flow, while `llm.normalization` only affects legacy helper paths and `llm.extraction` is currently not wired into any config-driven runtime call.
- This mismatch makes it hard to know which knobs still matter and increases the chance of paying for or tuning the wrong stage.

## In Scope

- Audit the effective runtime usage of `llm`, `llm.extraction`, `llm.normalization`, `llm.decision`, and `llm.stl_extraction`.
- Repair dead or misleading config wiring so any documented stage override is either genuinely consumed or explicitly treated as a legacy-only option.
- Update default TOML files and documentation so they reflect current runtime reality.
- Add regression tests that lock the stage semantics in place.

## Out Of Scope

- Replacing the STL-native `add()` architecture.
- Broad cost optimization beyond clarifying and fixing stage selection semantics.

## Proposed Changes

- Keep only `llm.stl_extraction` and `llm.decision` as first-class stage overrides for the current `Memory.add()` path.
- Remove legacy fact extraction / normalization helper APIs and their prompt/config surfaces when they are not required by the maintained business path.
- Remove `llm.extraction` and `llm.normalization` from default TOML files and stop treating them as supported runtime knobs.
- Update README/config guidance to distinguish the active add-path stages from the removed legacy pipeline.

## Reality Check

- The current code already proves that not every configured stage is equally meaningful:
  - `stl_extraction` is used by `Memory.add()`.
  - `decision` is used when projecting STL statements into owner-centered memories.
  - `normalization` is only used by compatibility helpers such as `_normalize_single_fact()` / `_process_fact()`.
  - `extraction` is instantiated on `Memory`, but no current config-driven runtime path uses `self.extraction_llm`.
- Simply deleting legacy stage support would be the cleanest internal shape, but it would conflict with the repo’s existing compatibility helpers and living specs.
- The safer direction is narrower:
  - make any still-documented stage override genuinely effective,
  - remove misleading default config blocks for stages that are not on the default `add()` path,
  - document the compatibility boundary clearly.

## Acceptance Signals

- A developer can tell from `mind.toml`, `mindt.toml`, and `README.md` which stage overrides affect the current `Memory.add()` path.
- Any stage override still documented as supported is exercised by a real runtime call path and covered by tests.
- The default config files no longer imply that legacy-only stages are part of the mainline STL-native add pipeline.

## Verification Plan

- Profile: `full`
- Checks:
  - `workflow-integrity`
  - `stage-usage-audit`
  - `config-runtime-alignment`
  - `doc-config-alignment`
  - `behavior-regression`
- Automated verification will rely on focused pytest coverage plus a full `pytest -q tests` run.

## Open Questions

- None blocking implementation. The direction is to remove the legacy helper path rather than preserve it.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
