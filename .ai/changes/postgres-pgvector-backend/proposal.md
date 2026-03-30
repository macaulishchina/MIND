# Change Proposal: Postgres + pgvector Storage Backend

## Metadata

- Change ID: `postgres-pgvector-backend`
- Type: `refactor`
- Status: `complete`
- Spec impact: `none`
- Verification profile: `refactor`
- Owner: `Codex`
- Related specs: `memory-add-extraction`

## Summary

- Replace the current Qdrant + SQLite storage pairing with a Postgres + pgvector-backed path while preserving the existing `Memory` API and add/search/update/delete/history behavior.

## Why Now

- The current storage split makes state management and consistency reasoning harder than needed for a memory system whose source data is already relational in shape.
- A Postgres + pgvector path keeps structured memory state and vector search in one database without changing the higher-level memory pipeline.

## In Scope

- Add a Postgres + pgvector vector-store implementation compatible with the existing `BaseVectorStore` contract.
- Add a Postgres-backed history store implementation compatible with the current history API.
- Wire configuration and factories so `Memory` can use the Postgres-backed implementations.
- Update example and test configuration needed to exercise the new backend.
- Preserve current add/search/update/delete/history semantics.

## Out Of Scope

- Retrieval quality improvements such as score thresholds, reranking, or hybrid retrieval.
- Prompt changes, extraction changes, or decision-policy changes.
- Broader repository architecture cleanup beyond what is required to support the new backend.
- Data migration tooling for existing external Qdrant or SQLite deployments.

## Proposed Changes

- Introduce a `pgvector` vector store provider that stores current memories in Postgres rows with an embedding column.
- Introduce a Postgres history store provider that stores operation history in a `memory_history` table in the same database.
- Keep the runtime `Memory` orchestration unchanged; only the persistence backend and its configuration surface are replaced.
- Keep behavior parity for logical delete, versioned update, payload-to-item mapping, and per-user active-memory filtering.

## Reality Check

- The current repo has no pre-existing Postgres abstraction, so this change must add the minimum new configuration and factory wiring needed to avoid leaking backend-specific logic into `Memory`.
- The repo currently has deterministic local tests built around fake LLM and embedding backends plus in-memory Qdrant and SQLite. A fully automated Postgres integration path may require extra local infrastructure, so verification may need a mix of automated and manual evidence.
- Cross-backend transactionality is intentionally not being solved here. This change narrows storage to one database technology, but it does not redesign write ordering or introduce stronger transactional semantics beyond the existing behavior.
- A narrower alternative would be to add Postgres + pgvector as an optional backend while leaving current defaults intact. That is implementation-friendly and reduces test disruption, but the resulting system still carries both storage paths in code. This change accepts that tradeoff to preserve behavior while enabling the new backend immediately.

## Acceptance Signals

- `Memory.add()`, `search()`, `get()`, `get_all()`, `update()`, `delete()`, and `history()` continue to work through the existing public API.
- The Postgres-backed vector store returns the same result shape currently expected by retrieval and search flows.
- The Postgres-backed history store preserves history ordering and metadata.
- Existing behavior-oriented tests continue to pass or are replaced with equivalent coverage for the new backend path.

## Verification Plan

- Profile: `refactor`
- Checks:
  - `workflow-integrity`: change artifacts are present and reflect the implemented scope.
  - `behavior-parity`: run targeted automated tests for memory and storage behavior, plus manual review of add/search/update/delete/history paths where automation cannot cover the full backend.
  - `config-wiring`: verify config resolution and factory selection for the new providers.
- Manual review may be used where local Postgres + pgvector infrastructure is unavailable or impractical.

## Open Questions

- None blocking implementation. The migration direction and parity-only scope were already established before this change started.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
