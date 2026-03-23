# Checklist: Bug Fix

Use this checklist when fixing a bug.

---

## Investigation

- [ ] Reproduce the bug with a failing check or test when practical
- [ ] If the fix spans many files or multiple steps, create or update `PLANS.md`
      from `.ai/templates/PLANS.md`
- [ ] Identify the root cause, not just the symptom
- [ ] Check nearby code paths for the same failure mode

## Fix

- [ ] Make the minimal change needed to fix the root cause
- [ ] Avoid unrelated cleanup in the same change

## Testing

- [ ] The failing check now passes
- [ ] Add regression coverage if the bug could recur
- [ ] Run the repo's available validation commands, or note the manual checks
      you used instead

## Documentation

- [ ] Update any stale `.ai/` guidance the bug exposed
