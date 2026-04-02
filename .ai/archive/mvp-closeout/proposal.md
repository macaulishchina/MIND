# Change Proposal: MVP Closeout Baseline

## Metadata

- Change ID: `mvp-closeout`
- Type: `feature`
- Status: `archived`
- Spec impact: `update required`
- Verification profile: `full`
- Owner: `agent`
- Related specs: `mvp-release-readiness`

## Summary

- Close the remaining MVP gap between the implemented codebase and the
  repository's user-facing MVP documentation and acceptance baseline.

## Why Now

- The core `Memory` pipeline is already implemented, but the repository still
  lacks one durable MVP acceptance baseline that ties together quickstart docs,
  public API smoke coverage, and known MVP limits.
- README still contains at least one stale eval command, which makes the MVP
  harder to run than the codebase reality suggests.

## In Scope

- Fix stale MVP-facing quickstart/eval documentation.
- Document the maintained MVP acceptance checklist and known limitations.
- Add one focused smoke test that exercises the public `Memory` API surface
  expected from the MVP.
- Add and merge a living spec for MVP release readiness.

## Out Of Scope

- New STL prompt optimization work.
- v1.5 features such as confidence decay, time decay, or memory merge.
- v2 retrieval enhancements.
- Release tagging, packaging, or deployment automation.

## Proposed Changes

### 1. Align README with the maintained MVP entrypoints

- Replace stale eval commands with the unified `eval_cases.py` runner.
- Document the recommended MVP path for configuration and validation.

### 2. Refresh MVP-facing core docs

- Update the MVP definition and evaluation plan under `Doc/core/` so they
  describe the current STL-native architecture, supported public API surface,
  success criteria, and known limitations.

### 3. Add a durable MVP acceptance baseline

- Introduce a living spec that defines MVP release readiness in terms of:
  maintained docs, a public API smoke path, and explicit MVP limitations.

### 4. Add one public API smoke test

- Add a focused test that uses the public `Memory` methods to exercise:
  `add`, `search`, `get`, `get_all`, `update`, `delete`, and `history`.

## Reality Check

- The earlier MVP task list included “打一个 MVP 版本基线”, but versioning or
  release automation is not required to make the repository MVP-ready. The
  narrower and more repo-realistic direction is to define the acceptance
  baseline first.
- Some older `Doc/core/` materials describe an earlier architecture (for
  example, a pre-STL natural-language extraction flow and narrower backend
  assumptions). Leaving them untouched would keep the MVP story internally
  inconsistent.
- This change should not try to settle post-MVP roadmap questions. If we mix
  v1.5/v2 direction into MVP closeout, the scope will expand without improving
  immediate release readiness.

## Acceptance Signals

- README quickstart/eval guidance uses maintained commands that exist in the
  repository.
- A durable MVP acceptance/limitations baseline exists in repo docs and living
  specs.
- One focused smoke test covers the MVP public API surface and passes.
- The full pytest suite still passes.

## Verification Plan

- Profile: `full`
- Automated evidence: run `.venv/bin/python -m pytest tests/`
- Manual evidence: review README and `Doc/core/` docs for command correctness,
  MVP scope alignment, and known-limitation clarity.
- Required checks: `workflow-integrity`, `change-completeness`,
  `spec-consistency`, `manual-review`

## Open Questions

- None blocking. This change deliberately limits itself to MVP closeout rather
  than post-MVP feature work.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
