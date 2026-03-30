# Change Proposal: MVP Implementation

## Metadata

- Change ID: `mvp-implementation`
- Type: `feature`
- Status: `approved`
- Spec impact: `update required`
- Verification profile: `full`
- Owner: `AI + Human`
- Related specs: `none (first implementation)`

## Summary

Implement the MIND MVP: a memory quality layer that can add, search, update,
and delete memories with confidence scoring, source context tracking, and
version history. This is the first code in the repository.

## Why Now

The repository currently contains only workflow scaffolding and design documents.
All design decisions are finalized in `Doc/`. The MVP is the necessary first
step to validate the core memory loop before any quality enhancements.

## In Scope

Based on `Doc/MVP定义.md` and `Doc/架构设计.md`:

1. **Data model**: `MemoryItem` with core layer (7 fields) + enhancement layer
   (confidence, status, source_context, source_session_id, version_of,
   importance, type)
2. **Memory class**: single entry point with `add`, `search`, `get`, `get_all`,
   `update`, `delete`, `history` methods
3. **LLM layer**: Factory interface + OpenAI implementation (GPT-4o-mini)
4. **Embedding layer**: Factory interface + OpenAI implementation
   (text-embedding-3-small)
5. **Vector store layer**: Factory interface + Qdrant implementation
   (in-memory for dev)
6. **History storage**: SQLite for operation history tracking
7. **Prompt engineering**: fact extraction prompt (with confidence output) +
   update decision prompt (ADD/UPDATE/DELETE/NONE)
8. **Enhancement fields written at v1**: confidence, source_context, version_of
9. **Logical delete**: status=active/deleted, search filters on active only
10. **Project scaffolding**: requirements.txt, README.md, basic test suite

## Out Of Scope

- Multi-user / multi-agent support
- Graph memory
- Forgetting mechanisms (v1.5)
- Query decomposition and multi-path retrieval (v2)
- Complex state machine (v2)
- Background consolidation tasks
- Web UI
- Ollama or other non-OpenAI backends (Factory interface reserved)
- Production Qdrant server deployment

## Proposed Changes

### Code Structure

```
mind/
├── __init__.py           # Package exports
├── memory.py             # Memory main class (single entry point)
├── config.py             # MemoryConfig, MemoryItem, enums
├── prompts.py            # LLM prompt templates
├── llms/
│   ├── __init__.py
│   ├── base.py           # BaseLLM abstract class
│   ├── factory.py        # LlmFactory
│   └── openai.py         # OpenAI LLM implementation
├── embeddings/
│   ├── __init__.py
│   ├── base.py           # BaseEmbedding abstract class
│   ├── factory.py        # EmbedderFactory
│   └── openai.py         # OpenAI embedding implementation
├── vector_stores/
│   ├── __init__.py
│   ├── base.py           # BaseVectorStore abstract class
│   ├── factory.py        # VectorStoreFactory
│   └── qdrant.py         # Qdrant implementation
├── storage.py            # SQLiteManager for history
└── utils.py              # Helpers (hash, ID generation, message parsing)
tests/
├── __init__.py
├── test_memory.py        # End-to-end memory tests
├── test_storage.py       # SQLite history tests
└── conftest.py           # Shared fixtures
requirements.txt
README.md
```

### Core Flow

**Add flow** (two LLM calls):
1. Parse messages → LLM extracts facts with confidence → for each fact:
   embed → vector search top-5 → LLM decides ADD/UPDATE/DELETE/NONE →
   execute operation → record history

**Search flow**:
1. Embed query → vector search (filter status=active) → return top-K sorted
   by similarity

**Update flow** (manual):
1. Re-embed content → update vector store → record history

**Delete flow**:
1. Mark status=deleted (logical delete) → record history

### Key Design Decisions

- Enhancement fields exist in the data model from day one but are not used in
  retrieval or ranking at v1
- UPDATE creates a new memory with version_of pointing to the old memory;
  old memory remains active (v2 introduces superseded status)
- Temporary IDs in the update decision prompt to prevent LLM UUID hallucination
  (borrowed from mem0)
- Factory pattern for LLM/Embedding/VectorStore; only OpenAI + Qdrant
  implemented at v1

## Reality Check

### What could go wrong

1. **Qdrant in-memory mode limitations**: in-memory Qdrant loses data on
   restart. This is acceptable for MVP development and testing but must not
   be confused with production readiness.

2. **OpenAI API dependency**: all LLM and embedding calls require a valid
   OpenAI API key and network access. Tests need either mocking or a real key.

3. **Prompt quality risk**: the fact extraction and update decision prompts are
   the most critical component. Poor prompts will cascade into bad memories.
   We should reference mem0's proven prompts as a starting point and iterate.

4. **Scope creep risk**: the MVP document is well-bounded, but implementing
   the full Memory class with 7 methods plus 3 layers of abstraction is
   substantial. Strict adherence to the implementation order in `Doc/MVP定义.md`
   §7 will keep focus.

### Conflicts with existing state

- No conflicts — the repo has no existing code.

### Feasibility assessment

- All components are well-understood: OpenAI API, Qdrant client, SQLite,
  Python dataclasses/pydantic. No research unknowns in the MVP scope.
- The design documents are thorough and internally consistent.
- Estimated implementation: ~800-1200 lines of production code + ~200 lines
  of tests.

## Acceptance Signals

From `Doc/MVP定义.md` §6 and `Doc/评测方案.md` §3:

1. User says "我喜欢黑咖啡" → new session search for drink recommendations
   correctly recalls the preference
2. User changes to "我现在只喝美式" → system updates memory with version_of
   relationship
3. Deleted memory does not appear in search results
4. Every memory has confidence and source_context recorded
5. `history()` returns the change log for a given memory

## Verification Plan

- Profile: `full` (first substantial implementation, multiple risks)
- Checks requiring explicit evidence:
  - `behavior-parity`: N/A (no prior behavior)
  - `spec-consistency`: verify implementation matches Doc/ design documents
  - `change-completeness`: all 4 core operations + history work end-to-end
  - `manual-review`: run the 4 test scenarios from `Doc/评测方案.md` §3
- Manual review will be primary verification method since no CI exists yet

## Open Questions

None — all design decisions are finalized in the Doc/ directory and confirmed
by the user.

## Approval

- [x] Proposal reviewed
- [x] Important conflicts and feasibility risks surfaced
- [x] Spec impact confirmed
- [x] Ready to finalize tasks and implement
