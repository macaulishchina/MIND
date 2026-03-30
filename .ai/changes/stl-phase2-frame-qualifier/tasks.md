# Tasks: STL Phase 2 — Frame + Qualifier

## Preconditions

- [x] Phase 1 complete: 52 STL tests + 25 existing = 77 total pass
- [x] Proposal approved

## Implementation

- [x] 1. Create `mind/stl/vocab.py` — seed vocabulary (42 predicates with categories)
- [x] 2. Add `get_vocab_category()` to BaseSTLStore + impls (lookup predicate → category)
- [x] 3. Update `store_program()` — resolve category for each statement before insert
- [x] 4. Add `insert_temporal_spec()` abstract method + SQLite/Postgres impls
- [x] 5. Detect `time()` qualifiers in `store_program()` → populate `temporal_specs`
- [x] 6. Add `mark_superseded()` + `_handle_correction()` for correct/retract workflow
- [x] 7. Add `seed_vocab()` to BaseSTLStore, called on init for both backends
- [x] 8. Write tests for category assignment (seed vocab + NEW_PRED created vocab)
- [x] 9. Write tests for temporal_specs population
- [x] 10. Write tests for correct_intent / retract_intent correction workflow
- [x] 11. Run full suite: 102 passed, 0 failures, 0 regressions

## Closeout

- [x] 12. Create verification-report.md
