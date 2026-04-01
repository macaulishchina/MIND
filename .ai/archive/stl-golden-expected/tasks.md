# Tasks: STL Golden Expected Output

## Status: COMPLETE

### T1: Add `expected_stl` to all case files ☑
- Wrote canonical v2 STL for each case
- All 18 case files have `stl_extract` stage with `expected_stl`

### T2: Add `stl_syntax_rate` metric to `eval_cases.py` ☑
- Compute ParseLevel breakdown for actual output
- Added to `StlExtractCaseResult` and report

### T3: Include `expected_stl` in eval report ☑
- Shows expected_stl alongside actual stl_text in case results

### T4: Update tests ☑
- Case loading works with new field
- Metric computation verified

### T5: Run full test suite ☑
- 190 tests passing
