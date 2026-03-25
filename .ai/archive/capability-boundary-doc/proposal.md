# Change Proposal: Add AI Memory Capability Boundary And Breakthrough Roadmap

## Metadata

- Change ID: `capability-boundary-doc`
- Type: `feature`
- Status: `archived`
- Spec impact: `none`
- Verification profile: `quick`
- Owner: `Codex`
- Related specs: `none`

## Summary

- Add a project document under `Doc/` that clearly defines the capability ceiling, module dependency points, required breakthroughs, and future research directions for the AI Memory architecture.

## Why Now

- The project already has planning, MVP, architecture, data model, evaluation, and technology roadmap documents.
- What is still missing is a durable statement of the system's real upper bound, what determines each module's capability, and what must be researched to push beyond the current architecture.

## In Scope

- Add `Doc/能力边界与突破路线图.md`
- Explain the capability ceiling of the current external-memory architecture
- Map major modules to their implementation dependencies and limiting factors
- Summarize breakthrough points, research topics, and likely future directions
- Record this docs-only change in workflow artifacts

## Out Of Scope

- Runtime implementation
- `.ai/specs/` updates
- Concrete API or schema changes
- Benchmark automation

## Proposed Changes

- Turn the architectural and roadmap discussion into a capability-boundary document that can guide later design choices and research prioritization.
- Clarify what the current architecture can do well, what it can only do weakly, and what it cannot do without entering a next-generation route.

## Reality Check

- It is easy to overestimate what a strong external-memory system can achieve; this document should explicitly call out where the current route stops.
- A vague “future work” section would not be enough; the document needs to separate engineering upgrades from actual research problems.
- The project still has no implementation, so the document should stay focused on architectural capability limits rather than pretend that unresolved model-learning problems already have engineering answers.

## Acceptance Signals

- The document makes clear what the external-memory route can and cannot achieve.
- Each major module has an explicit dependency on concrete implementation points.
- The breakthrough topics are prioritized and linked to plausible technical directions.

## Verification Plan

- Use the `quick` profile because this is a narrow project-doc addition.
- Satisfy `workflow-integrity`, `change-completeness`, and `manual-review` with manual artifact inspection.
- Record manual evidence because there is no automation for project-level documentation quality in this repository.

## Open Questions

- No blocking questions remain for this document.
- Exact future model-learning approaches remain intentionally open.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
