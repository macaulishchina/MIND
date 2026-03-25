# Change Proposal: Bootstrap Project Docs From Zero

## Metadata

- Change ID: `project-doc-bootstrap`
- Type: `feature`
- Status: `archived`
- Spec impact: `none`
- Verification profile: `quick`
- Owner: `Codex`
- Related specs: `none`

## Summary

- Add the first executable project documents under `Doc/` so the AI Memory project can move from a high-level vision into a concrete MVP starting point.

## Why Now

- The repository currently has a planning document but lacks the documents needed to begin focused implementation work.
- Without an MVP definition, architecture draft, memory model, and evaluation plan, early coding would be driven by chat decisions instead of durable project artifacts.

## In Scope

- Add `Doc/MVP定义.md`
- Add `Doc/系统架构草案.md`
- Add `Doc/记忆数据模型.md`
- Add `Doc/评测方案.md`
- Record this work in a docs-only change package

## Out Of Scope

- Runtime implementation code
- `.ai/specs/` product specs
- Storage vendor selection or deployment decisions
- Multi-agent memory, replay, or model fine-tuning design

## Proposed Changes

- Translate the existing planning document into a practical phase-one project definition.
- Define a narrow MVP, an implementation-friendly architecture slice, a first memory data model, and a manual evaluation baseline.

## Reality Check

- The current project is still at zero implementation, so these docs should enable a first build rather than over-specify a full platform.
- The existing planning document is broad and research-oriented; this change narrows it to a v1 that is realistic to prototype.
- Any detailed runtime API, storage topology, or model-learning strategy would be premature at this stage and is intentionally deferred.

## Acceptance Signals

- A new teammate can read the `Doc/` files and identify what to build first.
- The MVP scope is smaller than the original planning vision and can be implemented incrementally.
- The new docs align with the original planning document without copying its full breadth into v1 scope.

## Verification Plan

- Use the `quick` profile because this is a docs-only change with localized impact.
- Satisfy `workflow-integrity`, `change-completeness`, and `manual-review` with artifact inspection.
- Record manual verification because the repository has no automation for project docs.

## Open Questions

- No blocking questions for this first doc set.
- Concrete stack choices and runtime APIs remain deferred until implementation begins.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
