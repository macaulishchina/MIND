# Checklist: Refactoring

Use this checklist when refactoring existing code.

---

## Pre-work

- [ ] Define the refactoring goal in one sentence
- [ ] Confirm the refactor is requested or clearly necessary
- [ ] If the refactor spans many files or multiple steps, create or update
      `PLANS.md` from `.ai/templates/PLANS.md`

## Scope

- [ ] Keep the change limited to the stated goal
- [ ] Preserve behavior unless a behavior change is called out separately

## Execution

- [ ] Make changes in small, verifiable slices
- [ ] Check behavior after each meaningful step
- [ ] Record any recurring file coupling in `.ai/CHANGE_PROTOCOL.md`

## Testing

- [ ] Existing checks still pass, or the intended behavior change is documented
- [ ] Add focused coverage if the refactor creates a new abstraction with
      meaningful logic

## Verification

- [ ] Run the repo's available verification commands, or record the manual
      checks used instead
- [ ] Confirm the repository instructions still describe reality after the
      refactor
