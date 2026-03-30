# Change Proposal: Semantic Translation Layer — Phase 2

## Metadata

- Change ID: `stl-phase2-frame-qualifier`
- Type: `feature`
- Status: `approved`
- Spec impact: `none` (implementing existing spec)
- Verification profile: `feature`
- Owner: `ai-agent`
- Related specs: `Doc/core/语义翻译层.md` §6, §9, §11, §19
- Depends on: `semantic-translation-layer` (Phase 1, complete)

## Summary

Phase 1 delivered parser + store + pipeline rewiring. Frames and qualifiers
parse correctly (syntax-identical to props) but `category` is never set, seed
vocabulary is missing, time/qualifier-specific storage logic is absent, and
`correct_intent`/`retract_intent` are parsed but not acted upon.

Phase 2 makes frame/qualifier semantics fully operational:

1. Seed vocabulary (~30 predicates) pre-populated with category assignments.
2. Store-time category resolution — look up predicate in vocab, set
   `statements.category` before insert.
3. Qualifier-target linking — `time()`, `degree()`, etc. have their first arg
   recorded as a target statement for structured query.
4. `correct_intent`/`retract_intent` detection — trigger correction workflow
   (query matching statements, mark `is_current = FALSE`, set `superseded_by`).
5. Integration tests exercising the full pipeline with frame/qualifier examples
   from §11.

## In Scope

- Seed vocab data (`mind/stl/vocab.py`) with all ~30 seed predicates
- `store_program()` category resolution via vocab lookup
- `temporal_specs` population for `time()` qualifiers (write raw values;
  fuzzy resolution deferred to Phase 3)
- `correct_intent`/`retract_intent` detection + correction workflow stub
- Integration tests with frame/qualifier/correction examples

## Out Of Scope

- Focus stack / coreference resolution (Phase 3)
- Fuzzy time resolution (relative → absolute) (Phase 3)
- Vocab collision detection via embeddings (Phase 3)
- Evaluation framework adaptation

## Proposed Changes

1. New `mind/stl/vocab.py` — seed vocabulary definitions.
2. `store.py`: `store_program()` gains category resolution step.
3. `store.py`: new `insert_temporal_spec()` abstract method + impls.
4. `store.py`: new `_handle_correction()` method for correct/retract intents.
5. `store.py`: `query_statements_for_correction()` to find candidates.
6. Tests: `tests/test_stl_phase2.py` for category, temporal, correction.

## Reality Check

- Category resolution at store time (not parse time) is correct per spec:
  "This distinction does NOT affect parsing, only downstream queries."
- `correct_intent` matching is imprecise without embeddings. Phase 2 uses
  predicate + ref overlap heuristics. Phase 3 adds embedding similarity.
- Temporal specs store raw values; fuzzy→absolute resolution is Phase 3.
