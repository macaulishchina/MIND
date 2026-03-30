# Change Proposal: Semantic Translation Layer — Phase 3 (Runtime Enhancements)

## Metadata

- Change ID: `stl-phase3-runtime`
- Type: `feature`
- Status: `draft`
- Spec impact: `none` (implementing existing spec §17, §18, §9)
- Verification profile: `feature`
- Owner: `ai-agent`
- Related specs: `Doc/core/语义翻译层.md` §9, §17, §18
- Depends on: `stl-phase2-frame-qualifier` (Phase 2, complete)

## Summary

Phase 2 delivered category assignment, temporal specs storage, correction
workflow, and seed vocabulary.  Phase 3 makes the three remaining runtime
enhancements operational:

1. **Focus Stack / Coreference Resolution** (§17) — Track entity salience
   across turns and inject the top-k active entities into the LLM prompt
   before extraction.  Write coreference and coref_pending records.
2. **Fuzzy Time Resolution** (§18) — Resolve relative time expressions
   ("next_month", "last_year", "this_weekend") to absolute dates using the
   turn timestamp as anchor.  Update `_classify_time_value` to perform the
   resolution and store `anchor_turn` correctly.
3. **Vocabulary Collision Detection** (§9) — Before registering a NEW_PRED,
   compute its embedding and compare against existing vocab entries.  If
   similarity > 0.85, log a warning (soft alert, not blocking).

## Why Now

Phase 1 + Phase 2 cover parsing, storage, and semantic categorization.  The
three Phase 3 features are the last pieces specified in the design doc that
close the gap between "extract and store" and "extract correctly at scale":

- Without focus stack, LLM accuracy degrades in 20+ turn conversations.
- Without time resolution, "next_month" stored raw is useless for queries.
- Without collision detection, vocabulary bloats with near-synonyms.

## In Scope

### Focus Stack (§17)
- `mind/stl/focus.py` — `FocusEntry`, `FocusStack` data structures
- Five-dimension scoring: recency, frequency, grammar role, topic relevance,
  speaker proximity
- `FocusStack.update(program, current_turn)` — update scores after extraction
- `FocusStack.top_k_for_prompt()` → list of dicts for `format_focus_stack()`
- `BaseSTLStore.query_recent_refs(owner_id, limit)` — bootstrap from DB
- `BaseSTLStore.insert_coreference(source_expr, resolved_to, turn_id, confidence, method)`
- `BaseSTLStore.insert_coref_pending(source_expr, candidates, turn_id)`
- Wire into `Memory._extract_stl()` — populate focus stack before LLM call

### Fuzzy Time Resolution (§18)
- Enhance `_classify_time_value()` with `anchor_date` parameter
- Resolve relative expressions: `next_month → 2026-04`, `last_year → 2025`,
  `today_noon → 2026-03-30`, `this_weekend → 2026-04-04/2026-04-05`
- Pass turn timestamp through `_handle_time_qualifier()` → `anchor_turn`
- Store resolved values in `temporal_specs.resolved_start/resolved_end`

### Vocabulary Collision Detection (§9)
- `BaseSTLStore.check_vocab_collision(word, embedder)` — embed word, query
  existing vocab embeddings, return near-duplicates (sim > 0.85)
- Add `embedding` column to `vocab_registry` table (nullable BLOB/vector)
- Call collision check in `_handle_new_pred()` before registration
- Log warning on collision; register anyway (soft alert per spec)

### Tests
- `tests/test_stl_phase3.py` — focus stack scoring, time resolution,
  vocab collision detection

## Out Of Scope

- Topic relevance dimension (T): requires embedding similarity between
  current turn text and entity context.  Initial implementation will use a
  placeholder constant (0.5) and document for future enhancement.
- Vocab lifecycle state transitions (candidate → established → seed → dormant):
  tracked by usage_count already; automatic promotion deferred.
- Zero-anaphora detection in Chinese text (the focus stack enables it but
  actual detection requires NLP parsing beyond current scope).
- PostgresSTLStore — add abstract methods and SQLite impls; Postgres impls
  follow the same pattern and will be added symmetrically.

## Proposed Changes

1. New `mind/stl/focus.py` — FocusEntry, FocusStack classes.
2. `mind/stl/store.py` — add `query_recent_refs()`, `insert_coreference()`,
   `insert_coref_pending()` abstract methods + SQLite impls.  Extend
   `_handle_time_qualifier` with anchor_date.  Add `check_vocab_collision()`.
3. `mind/stl/store.py` — add nullable `embedding` column to vocab_registry
   schema.
4. `mind/stl/store.py` — enhance `_classify_time_value()` with anchor_date.
5. `mind/memory.py` — wire focus stack into `_extract_stl()`.
6. `mind/stl/prompt.py` — `format_focus_stack()` already implemented, no
   changes needed.
7. Tests: `tests/test_stl_phase3.py`.

## Reality Check

- **Focus stack scoring without topic embeddings**: The T dimension requires
  embedding the current turn and comparing to entity context.  This adds an
  extra embedding call per extraction.  We use a constant placeholder (0.5)
  initially — the other four dimensions still provide significant signal.
- **Time resolution precision**: Relative expressions like "this_weekend"
  depend on locale.  We use a simple English/Chinese mapping and document
  the limitation.
- **Vocab collision without stored embeddings**: First-time collision check
  must embed all existing vocab words.  This is O(N) embedding calls for N
  vocab entries.  Mitigation: cache embeddings in the `embedding` column;
  lazy-compute only when checking collisions for new words.
- **Schema migration**: Adding `embedding` column to vocab_registry requires
  ALTER TABLE for existing DBs.  SQLite supports `ALTER TABLE ADD COLUMN`
  natively.  We add it in `create_schema()` with IF NOT EXISTS logic.

## Acceptance Signals

- Focus stack correctly identifies top-k entities from stored refs/statements
- `format_focus_stack()` output is injected into LLM prompt
- Relative time values are resolved to absolute dates given an anchor
- NEW_PRED registration logs collision warning when sim > 0.85
- All Phase 1 + Phase 2 tests continue passing (no regressions)
- New Phase 3 tests cover each feature

## Verification Plan

- Profile: `feature`
- Run full test suite: `uv run pytest tests/ -x`
- Manual review: focus stack prompt injection format
- Manual review: time resolution correctness for edge cases

## Open Questions

(None — spec designs from §9, §17, §18 are clear and actionable.)
