# Proposal: STL Golden Expected Output in Test Cases

## Problem

1. **Test cases lack correct STL intermediate results** — Currently cases only
   have semantic-level expectations (`expected_refs`, `expected_statements`,
   `expected_evidence`) but NOT the actual expected raw STL text. Without a
   golden reference, there's no way to verify format/syntax consistency.

2. **LLM-generated STL is inconsistent across models** — Different LLMs produce
   wildly different output: different predicate names, different local IDs,
   missing evidence lines, incorrect formatting, etc.

3. **STL format/syntax consistency is critical** — STL is the core intermediate
   layer. The generated output must be nearly consistent in format and syntax
   regardless of which LLM is used.

## Proposed Changes

### 1. Add `expected_stl` to case JSON schema

Each case's `stages.stl_extract` gains a new field:

```json
"stl_extract": {
  "expected_stl": "@s = @self\n$p1 = name(@s, \"John\")\nev($p1, conf=1.0, span=\"My name is John\")",
  "expected_refs": [...],
  "expected_statements": [...],
  "expected_evidence": [...]
}
```

The `expected_stl` is the canonical/golden STL text — the correct output that
any compliant LLM should produce (modulo local ID naming like `@s` vs `@self`).

### 2. Add syntax quality metrics to `stl_extract` stage

New metrics in `eval_cases.py`:

- `stl_syntax_rate` — % of non-empty/non-comment lines parsed at strict level
  (ParseLevel.STRICT). Measures whether the LLM output is syntactically clean
  without needing fuzzy repair or LLM correction.

- `stl_structure_score` — compares structural completeness: does the actual
  output have the expected number of refs, statements, and evidence lines?

### 3. Include `expected_stl` vs actual `stl_text` in eval reports

The JSON report for `stl_extract` already includes `stl_text` per case.
Add `expected_stl` alongside for easy visual diff.

## Scope

- 18 case JSON files → add `expected_stl` where `stl_extract` stage exists
  or add a new `stl_extract` stage for cases that lack one
- `eval_cases.py` → add `stl_syntax_rate` metric
- `eval_cases.py` → include `expected_stl` in report output
- Tests → update for new fields

## Spec Impact

Adds a new field to case schema and new metrics — does not change existing
behavior or interfaces.

## Reality Check

- Writing golden STL requires care — must follow the spec exactly
- Local IDs (`@s`, `$p1`) are arbitrary naming conventions in expected_stl;
  the semantic checks (`expected_refs/statements/evidence`) remain the
  authoritative pass/fail criteria
- `expected_stl` primarily serves as reference documentation and syntax
  quality feedback, not as a strict text-equality requirement
