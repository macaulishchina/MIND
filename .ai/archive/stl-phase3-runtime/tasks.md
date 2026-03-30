# Tasks: stl-phase3-runtime

## Preconditions

- [x] Proposal status is `approved`
- [x] Phase 2 complete: 102 tests pass
- [x] Spec sections §9, §17, §18 finalized

## Implementation

- [x] 1. Create `mind/stl/focus.py` — FocusEntry, FocusStack with 5-dim scoring
- [x] 2. Add store abstract methods: `query_recent_refs()`, `insert_coreference()`, `insert_coref_pending()`, `get_all_vocab_words()`
- [x] 3. Implement SQLite + Postgres store methods for coreference + coref_pending + query_recent_refs + get_all_vocab_words
- [x] 4. Enhance `_classify_time_value()` with anchor_date for fuzzy→absolute resolution
- [x] 5. Pass turn timestamp through `_handle_time_qualifier()` → correct anchor_turn + anchor_date
- [x] 6. Add vocab collision detection: `check_vocab_collision()` + `_cosine_sim()` helper
- [x] 7. Wire `_handle_new_pred()` to call collision check when embedder available
- [x] 8. Wire focus stack into `Memory._extract_stl()` — populate from history via `query_recent_refs()`
- [x] 9. Write tests: 47 tests covering focus stack, time resolution, cosine sim, vocab collision, store coreference
- [x] 10. Run full suite: 127 tests pass (80 existing + 47 new), zero regressions

## Validation

- [ ] Execute the selected verification profile
- [ ] Create or update `verification-report.md`
- [ ] Record any manual verification performed
- [ ] Record any skipped checks and why

## Closeout

- [ ] Merge accepted spec updates into `.ai/specs/`
- [ ] Move the completed change folder into `.ai/archive/`
