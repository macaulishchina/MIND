# Tasks: mvp-implementation

## Preconditions

- [x] Proposal status is `approved`
- [x] Spec impact confirmed: `update required`
- [x] Verification profile selected: `full`
- [x] Open questions resolved

## Implementation

### Phase 1: Project Scaffolding
- [ ] 1.1 Create `requirements.txt` with dependencies
- [ ] 1.2 Create `mind/__init__.py` package export
- [ ] 1.3 Create `mind/utils.py` (ID generation, hash, message parsing)

### Phase 2: Data Model + Storage Layer (Doc/MVP定义 §7 Step 1)
- [ ] 2.1 Create `mind/config.py` — MemoryItem, MemoryConfig, enums
- [ ] 2.2 Create `mind/vector_stores/base.py` — BaseVectorStore abstract class
- [ ] 2.3 Create `mind/vector_stores/factory.py` — VectorStoreFactory
- [ ] 2.4 Create `mind/vector_stores/qdrant.py` — Qdrant implementation
- [ ] 2.5 Create `mind/storage.py` — SQLiteManager for history tracking

### Phase 3: LLM + Embedding Layer
- [ ] 3.1 Create `mind/llms/base.py` — BaseLLM abstract class
- [ ] 3.2 Create `mind/llms/factory.py` — LlmFactory
- [ ] 3.3 Create `mind/llms/openai.py` — OpenAI LLM implementation
- [ ] 3.4 Create `mind/embeddings/base.py` — BaseEmbedding abstract class
- [ ] 3.5 Create `mind/embeddings/factory.py` — EmbedderFactory
- [ ] 3.6 Create `mind/embeddings/openai.py` — OpenAI embedding implementation

### Phase 4: Prompt Engineering (Doc/MVP定义 §7 Step 2)
- [ ] 4.1 Create `mind/prompts.py` — fact extraction + update decision prompts

### Phase 5: Memory Main Class (Doc/MVP定义 §7 Steps 2-4)
- [ ] 5.1 Create `mind/memory.py` — Memory class with all 7 methods
  - `add()`: two-step LLM flow (extract facts → decide operations)
  - `search()`: embed query → vector search (filter active) → return top-K
  - `get()`: retrieve single memory by ID
  - `get_all()`: retrieve all memories for a user
  - `update()`: manual update with re-embedding
  - `delete()`: logical delete (status=deleted)
  - `history()`: return operation history for a memory

### Phase 6: Tests + README
- [ ] 6.1 Create `tests/conftest.py` — shared fixtures
- [ ] 6.2 Create `tests/test_storage.py` — SQLite history tests
- [ ] 6.3 Create `tests/test_memory.py` — end-to-end memory tests
- [ ] 6.4 Create `README.md` — project overview, setup, usage examples

## Validation

- [ ] Execute the selected verification profile (`full`)
- [ ] Create `verification-report.md`
- [ ] Run the 4 test scenarios from `Doc/评测方案.md` §3
- [ ] Record results

## Closeout

- [ ] Create initial spec in `.ai/specs/` for the memory capability
- [ ] Move the change folder into `.ai/archive/`
