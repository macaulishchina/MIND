# Verification Report: mvp-closeout

## Metadata

- Change ID: `mvp-closeout`
- Verification profile: `full`
- Status: `complete`
- Prepared by: `agent`

## Checks Run

### `workflow-integrity`

- Result: `pass`
- Evidence: `proposal.md`, `tasks.md`, change-local spec delta, and this
  verification report are present under `.ai/archive/mvp-closeout/`.
- Notes: The proposal captured scope, reality check, and verification intent
  before implementation.

### `change-completeness`

- Result: `pass`
- Evidence:
  - README now uses the maintained `eval_cases.py` owner-add command
  - `Doc/core/MVP定义.md` and `Doc/core/评测方案.md` now describe the current
    STL-native MVP baseline
  - `tests/test_memory.py` now contains an MVP public API smoke path
  - Added living spec: `.ai/specs/mvp-release-readiness/spec.md`
- Notes: The change closes the requested MVP gap between implementation and
  acceptance/readiness documentation.

### `spec-consistency`

- Result: `pass`
- Evidence: The new `mvp-release-readiness` living spec, README/docs, and the
  smoke test all align on the same MVP baseline: maintained commands, explicit
  acceptance surface, and deleted-memory behavior on the public search surface.
- Notes: No post-MVP roadmap features were pulled into this change.

### `behavior-parity`

- Result: `pass`
- Evidence: `.venv/bin/python -m pytest tests/` -> `194 passed in 5.42s`
- Notes: The only user-visible behavior change is intentional: public
  `search()` no longer re-surfaces deleted facts through raw STL-only results.

### `manual-review`

- Result: `pass`
- Evidence:
  - Confirmed `README.md` no longer references the removed
    `eval_owner_centered_add.py` script
  - Confirmed `tests/eval/runners/eval_cases.py` is the maintained owner-add
    eval entrypoint documented in README and `tests/eval/README.md`
  - Confirmed `Doc/core/` MVP materials now describe the current STL-native
    path and explicit known limitations
- Notes: A live owner-add eval run was not used as evidence because `mindt.toml`
  may trigger real model calls depending on local secrets/config.

## Residual Risk

- MVP readiness is now documented and smoke-tested, but release packaging,
  tagging, and deployment automation remain intentionally out of scope.
- The decision-stage online default is still a global-default fallback rather
  than a separately benchmarked runtime profile.

## Summary

- The `full` verification profile is satisfied.
- MVP-facing docs, acceptance criteria, and public API smoke coverage now match
  the current implemented baseline.
