# Change Proposal: Semantic Translation Layer — Phase 1

## Metadata

- Change ID: `semantic-translation-layer`
- Type: `feature`
- Status: `approved`
- Spec impact: `update required`
- Verification profile: `feature`
- Owner: `ai-agent`
- Related specs: `memory-add-extraction`, `owner-centered-memory`

## Summary

Replace the current two-step LLM extraction pipeline (extract facts → normalize
to FactEnvelope) with a single-step Semantic Translation Layer (STL). The LLM
outputs a compact symbolic syntax in 5 fixed forms (REF, PROP, FRAME, EV,
NOTE). A deterministic parser converts the output into relational DB records
across a 12-table schema.

Phase 1 scope: Ref + Prop + Evidence + Parser + DB Schema + hybrid search.
FRAME and QUALIFIER lines are parsed and stored (syntax identical to PROP) but
the prompt does not emphasize them.

## Why Now

The current pipeline has three structural deficiencies:
1. Two LLM calls per fact (extraction + normalization) — high cost, information
   loss between steps.
2. JSON output is fragile — format errors discard entire facts.
3. Only factual assertions representable — attitudes, conditions, hearsay,
   negation, uncertainty are lost.

The design spec (`Doc/core/语义翻译层.md`) is finalized and approved for coding.

## In Scope

- STL data models (parsed AST types)
- STL parser with 4-level cascade (strict → fuzzy → LLM → fallback note)
- Inline predicate expansion to flat storage
- 12-table relational schema (Postgres + SQLite dual backend)
- STL extraction prompt (single LLM call)
- `Memory.add()` pipeline replacement
- Hybrid `Memory.search()` (vector + structured query)
- Conversation/turn persistence
- NEW_PRED detection and vocab registry
- Comprehensive tests (parser, store, integration)

## Out Of Scope

- Focus stack / coreference resolution (Phase 3)
- Time semantics resolution (Phase 3)
- Version control / correct_intent / retract_intent workflow (Phase 3)
- Vocab collision detection via embeddings (Phase 3)
- Evaluation framework adaptation for STL output format
- Migration tool for existing FactEnvelope data

## Proposed Changes

1. New `mind/stl/` package with `models.py`, `parser.py`, `store.py`,
   `prompt.py`.
2. `Memory.add()` becomes: owner resolution → single LLM call → parse →
   batch store. No per-fact concurrency needed.
3. `Memory.search()` adds structured SQL path alongside existing vector search.
4. New `STLStoreConfig` in config schema; new `[stl_store]` TOML section.
5. Remove normalization and decision LLM stages from the pipeline.
6. All 12 tables created from day one; Phase 2/3 tables exist but are
   unpopulated.

## Reality Check

- The parser must handle malformed LLM output gracefully. The 4-level cascade
  ensures no information is lost, but Level 3 (LLM correction) adds latency
  on parse failures. Accept this: correct parsing is more important than speed.
- Removing the decision LLM (ADD/UPDATE/DELETE) means STL Phase 1 always
  inserts new statements. Deduplication relies on `refs` upsert by
  `(scope, ref_type, key)` and `is_current` flags. This is acceptable for
  Phase 1; intelligent update/merge comes with correct_intent in Phase 3.
- The spec's `refs` table has no `owner_id`. Adding `owner_id` to `refs` and
  `statements` is necessary for multi-tenant support, consistent with the
  existing owner-centered architecture.
- Existing tests for FactEnvelope pipeline will break. They will be updated
  or replaced with STL-based tests.

## Acceptance Signals

- `pytest tests/test_stl_parser.py` passes: all line types, inline expansion,
  4-level cascade, §11 stress test examples.
- `pytest tests/test_stl_store.py` passes: 12 tables created, ref upsert,
  statement/evidence/note CRUD on both backends.
- `pytest tests/test_stl_integration.py` passes: `Memory.add()` with FakeLLM
  stores correctly; `Memory.search()` finds results.
- No regressions in unmodified tests.

## Verification Plan

- Profile: `feature`
- Checks: spec-consistency, workflow-integrity, change-completeness,
  manual-review
- Parser correctness verified by deterministic unit tests
- Store correctness verified by both SQLite (in-memory) and Postgres tests
- Integration verified with FakeLLM producing predefined STL output

## Open Questions

None — all design decisions resolved in spec review.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
