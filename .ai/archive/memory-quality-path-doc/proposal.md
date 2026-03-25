# Change Proposal: Add Memory Quality Improvement Path Document

## Metadata

- Change ID: `memory-quality-path-doc`
- Type: `feature`
- Status: `archived`
- Spec impact: `none`
- Verification profile: `quick`
- Owner: `Codex`
- Related specs: `none`

## Summary

- Add a project document under `Doc/` that explains the main and secondary paths for improving AI Memory quality, centered on but not limited to the retrieve-process-writeback loop.

## Why Now

- The project already defines MVP scope, architecture, technology roadmap, and capability boundaries.
- What is still missing is a durable explanation of the different ways memory quality can improve, so later implementation work does not reduce everything to only one loop or one storage choice.

## In Scope

- Add `Doc/记忆质量提升路径.md`
- Clarify the mainline path of memory quality improvement
- Distinguish supporting paths such as write gating, representation upgrades, and feedback loops
- Briefly call out longer-term enhancement routes beyond the current architecture
- Record this docs-only change in workflow artifacts

## Out Of Scope

- Runtime implementation
- `.ai/specs/` changes
- Benchmark code
- API or schema changes

## Proposed Changes

- Turn the recent discussion into a project document that can guide architecture and research prioritization.
- Explain that retrieve-process-writeback is the runtime mainline, but not the only path to better memory quality.

## Reality Check

- If this topic is not made explicit, teams often over-focus on retrieval quality and underinvest in write gating or representation quality.
- The document should be practical and layered, not a vague survey of every possible ML technique.
- Model-side learning is relevant but should stay clearly marked as a later-stage direction.

## Acceptance Signals

- The document clearly distinguishes core mainline and adjacent improvement paths.
- It aligns with existing project docs and the current external-memory architecture.
- A future implementer can use it to prioritize engineering and research work.

## Verification Plan

- Use the `quick` profile because this is a docs-only scoped addition.
- Satisfy `workflow-integrity`, `change-completeness`, and `manual-review` using artifact inspection.
- Record manual evidence because no automated validation exists for this class of document.

## Open Questions

- No blocking questions remain for this document.
- Quantitative evaluation of each path remains future work once implementation exists.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
