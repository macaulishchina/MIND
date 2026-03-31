# Change Proposal: Runtime Logging Alignment

## Metadata

- Change ID: `runtime-logging-alignment`
- Type: `bugfix`
- Status: `archived`
- Spec impact: `update required`
- Verification profile: `feature`
- Owner: `Codex`
- Related specs: `runtime-logging`

## Summary

- Make `logging.ops_llm`, `logging.ops_vector_store`, `logging.ops_database`, and `logging.verbose` apply consistently across runtime callers instead of only after `Memory._setup_logging()` happens to run first.

## Why Now

- Manual eval and the new latency runner can call LLMs directly without constructing `Memory`, which currently means ops logging may never be configured.
- The current setup mixes two separate concerns: logger handler setup and ops switch configuration.
- The user expectation is explicit: if config says relevant logging is enabled, the logs should appear regardless of which caller triggered the LLM, embedding, vector, or DB operation.

## In Scope

- Audit current logging initialization behavior across `Memory`, eval runners, and direct LLM usage.
- Introduce a caller-independent way to apply logging configuration from `MemoryConfig`.
- Make verbose ops detail honor config consistently when logging is enabled.
- Update docs and targeted tests to cover the intended behavior.

## Out Of Scope

- Redesigning the full log format.
- Adding new log categories beyond the current ops switches.
- Broad CLI logging flags for every runner.

## Proposed Changes

- Extract reusable runtime logging configuration so code that uses resolved config can initialize logging without going through `Memory`.
- Ensure ops switch refresh is not skipped just because the `mind` logger already has handlers.
- Preserve handler idempotency while allowing runtime config changes to refresh level, handlers, and ops switches safely.
- Update the latency runner to initialize logging from the provided TOML before making direct LLM calls.

## Reality Check

- The current owner-centered eval runner already works mostly by accident because it calls `Memory._setup_logging(cfg.logging)` up front, then later clones a config with `console=false`; subsequent `Memory(...)` instances do not reapply those changes because `_setup_logging()` returns early once handlers exist.
- The latency runner has no `Memory` dependency, so today it bypasses all logging setup and therefore never enables ops logging from config.
- Simply forcing verbose output inside callers would be the wrong fix because it would duplicate policy and violate the design goal that logging behavior comes from config, not the call site.
- Reconfiguring Python logging can be risky if done destructively; the change should update only the `mind` logger subtree and preserve idempotent behavior for unrelated loggers.

## Acceptance Signals

- Direct LLM calls made by the latency runner emit `🧠 [LLM]` logs when `logging.ops_llm=true` and `logging.console=true` or `logging.file` is configured.
- `logging.verbose=true` causes verbose prompt/output detail lines to appear for supported ops logs without requiring the caller to opt in separately.
- Reapplying logging config in the same process updates ops switches and handler behavior instead of silently keeping stale settings.
- Existing `Memory.add()` behavior remains unchanged apart from honoring the same centralized logging policy.

## Verification Plan

- Profile: `feature`
- Checks:
  - `spec-consistency`
  - `workflow-integrity`
  - `change-completeness`
  - `manual-review`
- Evidence will include focused pytest coverage and direct runner/manual command checks.

## Open Questions

- None blocking implementation. The main design choice is where the reusable logging bootstrap lives.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
