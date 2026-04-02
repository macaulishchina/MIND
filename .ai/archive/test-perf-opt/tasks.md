# Tasks: test-perf-opt

Proposal status: `approved`

## Implementation

- [x] 1. Install `pytest-xdist` and add to dev dependencies
- [x] 2. Configure default parallel execution in `pytest.ini`
- [x] 3. Run full suite with `-n auto` and verify all 190 tests pass
- [x] 4. Measure wall-clock time and confirm ≤ 30s (achieved ~12.8s)
- [x] 5. Optimize SQLiteSTLStore.seed_vocab() batch insert (1.2s → 0.24s per instance)
- [x] 6. Run 3x to verify no flakiness

## Validation

- [x] Execute the selected verification profile
- [x] Create `verification-report.md`

## Closeout

- [ ] Move the completed change folder into `.ai/archive/`