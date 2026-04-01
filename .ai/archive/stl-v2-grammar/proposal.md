# Change Proposal: STL v2 Grammar Redesign

## Metadata

- Change ID: `stl-v2-grammar`
- Type: `refactor`
- Status: `draft`
- Spec impact: `update required`
- Verification profile: `full`
- Owner: `agent`
- Related specs: `stl-evidence`

## Summary

Redesign the STL grammar from 5+1 line types to 3+1, optimized for LLM
generation reliability. Remove EV, remove inline nesting, remove list syntax,
remove local/world scope, add `:suggested_word` mechanism.

## Why Now

Eval results show LLM-generated STL is inconsistent across models. Main
failure modes: nested parentheses mismatch, unnecessary decisions (scope,
confidence), excessive output (ev lines ≈30-40% of output). A simpler grammar
directly reduces all three.

## In Scope

- New grammar spec (3+1 line types: REF, STMT, NOTE, COMMENT)
- EBNF formal grammar
- Argument restrictions (4 atomic types only)
- `:suggested_word` extension for predicate suggestion
- Seed vocabulary reorganization (semantic grouping)
- Complete example set
- Parser design guidance

## Out Of Scope

- Parser implementation (separate change)
- Prompt template rewrite (separate change)
- Database schema migration (separate change)
- Focus stack / coreference (unchanged)
- Test case updates (separate change)

## Proposed Changes

1. **Delete EV** — confidence/provenance handled by system, not LLM
2. **Delete inline nesting** — args are 4 atomic types only
3. **Delete list syntax** — multi-value always expanded to multiple STMTs
4. **Delete local/world scope** — REF simplified to `@id: TYPE "key"`
5. **Unify PROP/FRAME/QUALIFIER** — all become STMT, category is post-parse
6. **Add `:suggested_word`** — LLM suggests better predicates without inventing
7. **Simplify REF** — `@self` implicit, key optional for unnamed entities

## Reality Check

- Removing EV loses per-statement confidence. Acceptable because system-side
  inference from frame type is more reliable than LLM scoring.
- Removing inline nesting increases line count (~20-30%). Acceptable because
  each line is trivially parseable and LLM error rate drops significantly.
- Removing scope loses local/world distinction. Acceptable for single-owner
  MVP; can be reintroduced as a REF attribute later if needed.

## Acceptance Signals

- Grammar spec is unambiguous: every valid input has exactly one parse
- Grammar is LLM-friendly: fewer decisions, fewer tokens, simpler structure
- Existing v1 examples can all be expressed in v2

## Verification Plan

- Profile: full
- Grammar completeness: all v1 examples re-expressed in v2
- Ambiguity check: EBNF reviewed for conflicts
- Manual review of spec document

## Open Questions

- None remaining (all discussed and resolved in conversation)

## Approval

- [ ] Proposal reviewed
- [ ] Important conflicts and feasibility risks surfaced
- [ ] Spec impact confirmed
- [ ] Ready to finalize tasks and implement
