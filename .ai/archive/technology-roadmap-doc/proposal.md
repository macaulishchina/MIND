# Change Proposal: Add AI Memory Technology Evolution Roadmap

## Metadata

- Change ID: `technology-roadmap-doc`
- Type: `feature`
- Status: `archived`
- Spec impact: `none`
- Verification profile: `quick`
- Owner: `Codex`
- Related specs: `none`

## Summary

- Add a clear project-level technology evolution roadmap under `Doc/` that explains how the AI Memory system should evolve from a zero-base MVP into a stronger multi-layer memory architecture.

## Why Now

- The project now has MVP, architecture, data model, and evaluation documents, but it still lacks a concrete phased technology selection path.
- Without a technology roadmap, implementation work is likely to oscillate between storage-first, vector-first, and graph-first directions.

## In Scope

- Add `Doc/技术演进路线.md`
- Define phase-by-phase technology choices for memory storage, retrieval, lifecycle management, and future enhancement
- Record a docs-only workflow trail for this addition

## Out Of Scope

- Runtime implementation code
- `.ai/specs/` changes
- Concrete API design
- Production deployment scripts

## Proposed Changes

- Document a recommended `v1 -> v2 -> v3` technical evolution path
- Compare mainstream, emerging, and advanced memory technologies in the context of this project
- State which technologies should be adopted now, deferred, or only observed for later

## Reality Check

- The ecosystem changes quickly, but this repository still needs a durable near-term engineering recommendation instead of open-ended research notes.
- A roadmap that recommends too many technologies at once would increase implementation risk; the document should narrow choices rather than enumerate everything equally.
- Graph-based and model-side memory approaches are important, but starting there would overcomplicate a zero-base project that first needs transactional memory lifecycle control.

## Acceptance Signals

- A new engineer can read the roadmap and understand the recommended stack for `v1`, `v2`, and `v3`
- The roadmap aligns with existing project docs in `Doc/`
- The roadmap explicitly states what not to build first

## Verification Plan

- Use the `quick` profile because this is a docs-only scoped change
- Satisfy `workflow-integrity`, `change-completeness`, and `manual-review` using manual artifact inspection
- Record manual verification because no repository automation exists for this kind of document

## Open Questions

- No blocking questions remain for this roadmap draft
- Specific framework and language choices remain open until the first implementation change

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
