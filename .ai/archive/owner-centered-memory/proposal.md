# Change Proposal: Owner-Centered Structured Memory

## Metadata

- Change ID: `owner-centered-memory`
- Type: `feature`
- Status: `complete`
- Spec impact: `update required`
- Verification profile: `full`
- Owner: `Codex`
- Related specs: `memory-add-extraction`, `owner-centered-memory`

## Summary

- Replace the current text-only fact pipeline with an owner-centered memory flow that resolves a durable owner, derives owner-local subject references, normalizes extracted facts into structured envelopes, and stores canonical structured text for retrieval.

## Why Now

- The current pipeline cannot reliably model the difference between the current user, anonymous sessions, and third-party objects mentioned in conversation.
- Pure free-text facts make conflict handling and repeated references to the same third-party object unstable.
- The approved product direction now requires storing explicit facts without prompt-level exclusions for third-party or sensitive facts.

## In Scope

- Add owner resolution for known and anonymous conversations.
- Add owner-local subject references for self and third-party objects.
- Add structured fact envelopes and canonical structured text generation.
- Extend memory persistence with owner/subject/fact metadata and new relational tables for owners and subjects.
- Add stage-specific LLM configuration for extraction, normalization, and decision.
- Update prompts, fake LLM behavior, and tests to reflect the new extraction and canonicalization pipeline.

## Out Of Scope

- Global third-party entity resolution across multiple owners.
- Rich graph query APIs or a full standalone facts table as the system of record.
- Cost optimization beyond stage-specific model selection.
- Data migration tooling for pre-existing free-text memories.

## Proposed Changes

- Introduce an `OwnerContext` input model and resolve each `add()` call to a durable `owner_id`.
- Normalize extracted facts into a typed envelope carrying `owner_id`, `subject_ref`, `fact_family`, `field_key`, and `canonical_text`.
- Store structured canonical text such as `[friend:green] occupation=football player` instead of unconstrained natural-language memory text.
- Add `owners` and `owner_subjects` tables in the relational store and extend memory/history records with owner/subject metadata.
- Continue using vector retrieval, but narrow candidate selection by owner, subject, fact family, and field key before semantic ranking.

## Reality Check

- This is a behavior-changing feature with significant surface area: config parsing, prompt behavior, persistence, retrieval, and tests all need coordinated updates.
- The repository still carries Qdrant and SQLite backends in tests; owner/subject metadata must work there too, not only in the Postgres path.
- Full graph modeling would be a better long-term fit, but a light owner/subject layer is the narrower, lower-risk first step.
- Migration of existing memories is intentionally deferred; current data may remain in the old shape until explicit migration work is added later.

## Acceptance Signals

- `Memory.add()` accepts a structured owner context while keeping `user_id` as a compatibility alias.
- Known and anonymous owners are created or reused deterministically.
- Third-party mentions produce stable owner-local `subject_ref` values.
- Stored memory content is canonical structured text rather than unconstrained natural language.
- Existing CRUD behavior continues to work, with updates keyed by owner + subject + field semantics rather than only text similarity.

## Verification Plan

- Profile: `full`
- Checks:
  - `workflow-integrity`
  - `owner-resolution`
  - `subject-normalization`
  - `canonical-text-storage`
  - `behavior-regression`
  - `config-stage-overrides`
- Automated verification will cover unit and end-to-end tests; manual inspection will supplement any backend-specific gaps.

## Open Questions

- None blocking implementation. The product decisions in the approved implementation plan are treated as final for this change.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
