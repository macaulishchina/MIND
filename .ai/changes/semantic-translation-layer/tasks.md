# Tasks: semantic-translation-layer

## Preconditions

- Proposal status is `approved`
- Spec impact is confirmed: new capability spec required
- Verification profile: `feature`
- All design decisions resolved in `Doc/core/语义翻译层.md`

## Implementation

- [x] 1. Create `mind/stl/models.py` — parsed AST data models
- [x] 2. Create `mind/stl/parser.py` — STL parser (5 regex + bracket stack + 4-level cascade)
- [x] 3. Create `mind/stl/store.py` — BaseSTLStore + PostgresSTLStore + SQLiteSTLStore + factory
- [x] 4. Create `mind/stl/prompt.py` — STL extraction prompt
- [x] 5. Add `STLStoreConfig` to `mind/config/schema.py` and loading in `mind/config/manager.py`
- [x] 6. Update TOML configs (`mind.toml`, `mindt.toml`)
- [x] 7. Rewire `Memory.add()` to use STL pipeline
- [x] 8. Update `Memory.search()` for hybrid search
- [x] 9. Create `tests/test_stl_parser.py` — 33 tests, all pass
- [x] 10. Create `tests/test_stl_store.py` — 19 tests, all pass
- [ ] 11. Create `tests/test_stl_integration.py` — deferred to Phase 2
- [x] 12. Legacy code preserved (still used by eval runners); no dead code removal needed

## Validation

- [ ] Execute the selected verification profile
- [ ] Create or update `verification-report.md`
- [ ] Record any manual verification performed
- [ ] Record any skipped checks and why

## Closeout

- [ ] Merge accepted spec updates into `.ai/specs/`
- [ ] Move the completed change folder into `.ai/archive/`
