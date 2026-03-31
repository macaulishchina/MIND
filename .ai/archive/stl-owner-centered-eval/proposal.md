# Change Proposal: STL-Native Owner-Centered Evaluation

## Metadata

- Change ID: `stl-owner-centered-eval`
- Type: `feature`
- Status: `approved`
- Spec impact: `update required`
- Verification profile: `feature`
- Owner: `Codex`
- Related specs: `owner-centered-add-eval`, `memory-add-extraction`

## Summary

- Reintroduce a dedicated evaluation path for the real `Memory.add()` pipeline by making owner-centered evaluation STL-native instead of continuing to rely on extraction-only free-text fact matching.
- Reuse the current extraction datasets as migration inputs where they still provide valuable conversation coverage, but rewrite acceptance criteria around STL-backed state rather than `_extract_facts()` output.

## Why Now

- The runtime add path now extracts STL, parses it, stores structured statements, and embeds those statements; the maintained extraction eval still measures only `_extract_facts()`.
- The repository already carries an approved `owner-centered-add-eval` spec, while the old runner/tests were removed and skipped during STL migration.
- Several existing extraction expectations now conflict with STL goals, especially cases where hypotheticals, beliefs, quotes, uncertainty, or conditions should be preserved as frames rather than dropped as empty output.

## In Scope

- Define the STL-native evaluation direction for owner-centered `Memory.add()`.
- Specify how datasets should encode owner context, ordered turns, and expected STL-backed final state.
- Define the recommended migration strategy for `tests/eval/datasets/extraction_*.json`.
- Identify the metric surface for the future STL-native runner.

## Out Of Scope

- Changing STL extraction semantics in `Doc/core/语义翻译层.md`.
- Removing the legacy extraction runner or `_extract_facts()` contract in this proposal phase.
- Finalizing implementation tasks before proposal approval.

## Proposed Changes

- Center the next evaluation runner on `Memory.add()` rather than `_extract_facts()`, so cases are judged against parsed/stored STL-backed state.
- Extend the owner-centered dataset shape so each case can express:
  - owner identity
  - ordered chat turns
  - expected current refs/statements/evidence coverage
  - optional projected-memory assertions such as canonical text, subject ref, and update behavior
- Treat the existing extraction datasets as source corpora:
  - preserve conversation inputs, difficulty labels, and coverage metadata when useful
  - rewrite expectations into STL-native assertions
  - split cases that were only meaningful under the old free-text extraction contract
- Add STL-specific datasets that the old corpora do not cover well:
  - frame semantics (`hope`, `believe`, `say`, `if`, `neg`, `lie`)
  - qualifiers (`time`, `quantity`, `degree`, `location`)
  - corrections/retractions
  - multi-turn focus stack/coreference
  - new predicate registration via `note()`
- Keep `tests/eval/runners/eval_extraction.py` as a legacy regression tool, not the primary acceptance path for STL behavior.

## Reality Check

- Fully rewriting all existing extraction cases into STL assertions is likely too expensive to do blindly. A selective migration path is better: keep high-value inputs, discard cases that only test free-text phrasing quirks, and add fresh STL-native cases where semantics changed.
- The repo already has an approved `owner-centered-add-eval` spec and skipped tests referencing a removed runner. Creating a brand-new parallel evaluation concept would add confusion; reviving and tightening the owner-centered path is the narrower fit.
- Exact raw STL text is a poor assertion surface because local ids, ordering, and harmless prompt variation can differ. The runner should compare parsed/stored structure, not exact emitted lines.
- Some legacy "should extract nothing" cases are no longer correct under STL. For example, hypothetical, quoted, uncertain, or belief-bearing inputs may need frame statements instead of zero output.
- Deterministic testing may need fake-LLM support or fixture responses that can emit STL-shaped outputs, because the current fake backend is optimized for old fact extraction and normalization prompts.

## Acceptance Signals

- The change has an approved proposal and change-local spec delta aligned with repo reality.
- The chosen direction clearly states that STL-native owner-centered eval is the primary acceptance path for `Memory.add()`.
- Dataset requirements are specific enough that implementation can proceed without inventing a second incompatible schema.
- Migration guidance distinguishes reusable extraction corpora from cases that must be rewritten or replaced.

## Verification Plan

- Profile: `feature`
- Checks requiring evidence:
  - `spec-consistency`
  - `workflow-integrity`
  - `change-completeness`
  - `manual-review`
- For the proposal phase, evidence is manual review only.
- If implementation proceeds, add automated evidence for runner behavior and dataset loading.

## Open Questions

- Should the primary assertion surface be:
  - persisted STL relational state only, or
  - persisted STL state plus projected `MemoryItem` assertions?
- Should the first implementation migrate the current curated/relationship datasets, or start with the removed owner-centered datasets/tests and then backfill extraction-corpus migration?
- Do we want one STL-native dataset schema with optional sections, or separate dataset families for general, relationship, and frame-heavy cases?

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
