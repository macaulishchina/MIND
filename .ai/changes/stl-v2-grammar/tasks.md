# Tasks: STL v2 Grammar Redesign

## Task List

### Phase 1: Spec & Doc

- [x] T1: Write STL v2 grammar spec (`.ai/changes/stl-v2-grammar/spec.md`)
- [x] T2: Write proposal (`.ai/changes/stl-v2-grammar/proposal.md`)
- [x] T3: Get approval on spec
- [x] T4: Update `Doc/core/语义翻译层.md` to v2

### Phase 2: Parser & Models

- [x] T5: Rewrite `mind/stl/models.py` — remove ParsedEvidence, InlinePredArg, ListArg; add suggested_pred to ParsedStatement; simplify RefExpr
- [x] T6: Rewrite `mind/stl/parser.py` — new regex set, remove bracket-matching stack, remove LLM repair level, add `:suggested_word` extraction
- [x] T7: Update `mind/stl/vocab.py` — add `alias` to seed vocab, reorganize by semantic domain
- [x] T8: Rewrite `mind/stl/prompt.py` — STL v2 prompt template

### Phase 3: Storage

- [x] T9: Update `mind/stl/store.py` — remove insert_evidence, add suggested_pred to insert_statement, simplify ref upsert (no scope), remove evidence DDL

### Phase 4: Eval & Tests

- [x] T10: Update all 18 case JSON files — rewrite expected_stl to v2 syntax
- [x] T11: Rewrite `tests/test_stl_parser.py` to v2
- [x] T12: Update eval runners (eval_cases.py, eval_stl_extract.py) — remove evidence_accuracy metric
- [x] T13: Run full test suite and verify 0 failures (190 passed)

### Phase 5: Archive

- [x] T14: Merge spec into `.ai/specs/`
- [x] T15: Archive change folder
