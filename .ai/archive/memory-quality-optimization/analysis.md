# Memory Quality Optimization Analysis

> Status: **Draft** · Date: 2026-03-27 · Author: agent
>
> This document analyzes the current `add()` pipeline from a **memory quality
> and effectiveness** perspective, and proposes concrete optimization directions.

---

## 1. Current Pipeline Recap

```
add(messages, user_id)
│
├─ Phase 1: Fact Extraction          1× LLM call
│  └─ LLM extracts [{text, confidence}, ...] from conversation
│
├─ Phase 2: Per-Fact Processing      N× (EMB + VEC.search + LLM + write)
│  └─ For each fact (concurrently):
│     ├─ Embed fact → vector
│     ├─ Search similar existing memories
│     ├─ LLM decides: ADD / UPDATE / DELETE / NONE
│     └─ Execute the decision
│
└─ Return List[MemoryItem]
```

**LLM call count**: 1 (extraction) + N (per-fact decision) = **1 + N total**.

---

## 2. Optimization Dimensions

### 2.1 Batch Decision — Global View + Fewer LLM Calls

**Priority: 🔴 Critical · Impact: Quality ↑ + Performance ↑**

#### Problem

Each fact runs an **independent** decision LLM call. Facts cannot see each
other's decisions. This causes:

| Scenario | Current behavior | Ideal behavior |
|----------|-----------------|----------------|
| "之前在网易，刚跳到字节" → fact[0]="之前在网易" fact[1]="现在在字节" | Both UPDATE the same existing memory "在网易工作", one may overwrite the other | One merged UPDATE: "之前在网易，现在在字节" |
| "我叫张三" when "张三" already exists | Each fact independently decides NONE, correct but N LLM calls wasted | One batch call decides NONE for all duplicates |
| "不喜欢PHP了，开始学Rust" → fact[0]="不喜欢PHP" fact[1]="开始学Rust" | fact[0] DELETEs "喜欢PHP", fact[1] ADDs "学Rust" independently | One coherent decision: UPDATE "喜欢PHP" → "从PHP转向Rust" |

#### Proposed Solution

Replace N independent decision calls with **one batch decision call**:

```
Current:  for each fact → search → LLM(fact + similar) → action
Proposed: for each fact → search → collect all (fact + similar) pairs
          → LLM(ALL facts + ALL similar memories) → actions[]
```

**New prompt structure** (sketch):

```
Existing memories:
[0] 用户在网易工作
[1] 用户喜欢PHP
[2] 用户叫张三

New facts from this conversation:
(a) 用户之前在网易
(b) 用户刚跳槽到字节
(c) 用户叫张三
(d) 用户开始学Rust

For EACH new fact, decide: ADD / UPDATE / DELETE / NONE.
You may reference other new facts in your reasoning.
Return a list of decisions.
```

**Benefits**:
- LLM calls: 1 + N → **1 + 1 = 2** (regardless of fact count)
- Global context: LLM sees all facts together, can merge related decisions
- Conflict resolution: built into the single decision call

**Risks**:
- Longer prompt → higher token cost per call (but fewer calls overall)
- Single point of failure (one bad parse loses all decisions)
  - Mitigation: fall back to per-fact mode on parse failure

**Estimated effort**: Medium. Changes to `_process_fact` → `_process_facts_batch`,
new prompt template, parse logic for batch response.

---

### 2.2 Structured Fact Extraction — Category + Temporal

**Priority: 🟡 High · Impact: Foundation for search quality + lifecycle**

#### Problem

Current extraction produces flat `{text, confidence}` objects. No structure
beyond free-text. This limits:
- Search precision (can't filter by category)
- Lifecycle management (can't auto-expire time-bound facts)
- Analytics (can't answer "what do we know about user's preferences?")

#### Proposed Enhancement

Extend the extraction schema:

```json
{
  "facts": [
    {
      "text": "The user likes black coffee",
      "confidence": 0.95,
      "category": "preference",
      "temporal": "permanent"
    },
    {
      "text": "The user has a job interview next Monday",
      "confidence": 0.9,
      "category": "plan",
      "temporal": "2026-04-01"
    },
    {
      "text": "The user prefers short replies",
      "confidence": 0.8,
      "category": "interaction_preference",
      "temporal": "permanent"
    }
  ]
}
```

**Category taxonomy** (suggested):

| Category | Description | Example |
|----------|-------------|---------|
| `personal_info` | Name, age, location, family | "张三, 28岁" |
| `preference` | Likes, dislikes, tastes | "喜欢黑咖啡" |
| `professional` | Job, skills, workplace | "在字节做后端" |
| `plan` | Future events, goals | "下周一面试" |
| `health` | Health conditions, habits | "每天跑步5km" |
| `relationship` | Social connections | "女朋友叫小红" |
| `opinion` | Beliefs, views | "觉得AI会改变教育" |
| `interaction_preference` | How the user wants AI to behave | "不要太啰嗦" |

**Temporal types**:
- `permanent` — no expiry
- `YYYY-MM-DD` — expires after this date
- `session_only` — only relevant in current session

**Benefits**:
- Category enables filtered search (search within "preference" only)
- Temporal enables automatic expiry / cleanup
- `interaction_preference` captures a whole class of facts currently missed
- Structured data enables analytics and user profile summaries

**Estimated effort**: Low-Medium. Prompt change + schema extension + store
category/temporal in vector payload.

---

### 2.3 Memory Lifecycle Management

**Priority: 🟡 High · Impact: Long-term quality**

#### Problem

Memories are **write-once, never-decay**. Over time:
- Outdated memories persist with equal weight to fresh ones
- Fragmented memories accumulate ("喜欢咖啡" + "喜欢黑咖啡" + "喜欢冰美式")
- No capacity control — heavy users may accumulate thousands of memories

#### Proposed Mechanisms

##### 2.3.1 Time-Weighted Scoring

When searching, adjust score based on memory age:

```python
final_score = similarity_score * time_decay_factor(memory_age)

# Example decay function:
# - Last 7 days: 1.0
# - Last 30 days: 0.95
# - Last 90 days: 0.85
# - Last 365 days: 0.7
# - Older: 0.5
```

This doesn't delete old memories, just deprioritizes them in search results.

##### 2.3.2 Confidence-Weighted Scoring

Currently `confidence` is stored but never used in search. Incorporate it:

```python
final_score = similarity_score * confidence * time_decay_factor(age)
```

##### 2.3.3 Memory Compaction (Background)

Periodic task that:
1. Groups memories by user + category
2. Finds clusters of similar/overlapping memories
3. Merges them into a single, comprehensive memory via LLM
4. Archives the originals

```
Before compaction:
  [mem-1] "喜欢咖啡" (confidence: 0.8, 30 days old)
  [mem-2] "喜欢黑咖啡" (confidence: 0.9, 15 days old)
  [mem-3] "每天早上喝冰美式" (confidence: 0.95, 2 days old)

After compaction:
  [mem-4] "每天早上喝冰美式，偏好黑咖啡" (confidence: 0.95, 2 days old)
  [mem-1, mem-2, mem-3] → archived
```

##### 2.3.4 Capacity Policy

Per-user memory limit (configurable). When exceeded:
1. Score all memories: `confidence * time_decay * access_frequency`
2. Archive lowest-scoring memories until under limit

**Estimated effort**: Medium-High. Requires background task infrastructure,
scoring functions, compaction LLM prompt.

---

### 2.4 Search Quality Enhancement

**Priority: 🟠 Medium · Impact: Retrieval precision**

#### Problem

Current search is pure vector similarity with fixed top-K. This misses:
- Keyword-exact matches (user says "咖啡", memory says "coffee")
- Category-level filtering
- Score threshold cutoff (K=5 may return 3 irrelevant results)

#### Proposed Enhancements

##### 2.4.1 Dynamic K with Score Threshold

Instead of fixed `top_k=5`:

```python
results = vector_store.search(query_vector, limit=20)  # fetch more
filtered = [r for r in results if r["score"] >= min_similarity_threshold]
return filtered[:max_k]  # cap at max
```

##### 2.4.2 Category-Filtered Search

If fact has a category, pre-filter:

```python
# For a "preference" fact, search only in "preference" memories first
results = vector_store.search(
    query_vector=fact_vector,
    filters={"user_id": uid, "category": "preference", "status": "ACTIVE"},
)
# If too few results, fall back to unfiltered search
```

##### 2.4.3 Hybrid Search (Future)

Combine vector similarity + BM25 keyword search. Qdrant supports this
natively via its hybrid search API. Requires indexing text content as
a separate payload field with full-text index.

**Estimated effort**: Low (dynamic K, threshold) to Medium (hybrid search).

---

### 2.5 Pipeline LLM Call Efficiency

**Priority: 🟠 Medium · Impact: Cost + Latency**

#### Current vs Optimized Call Count

| Scenario (4 facts) | Current | With Batch Decision | With Batch + Category |
|---------------------|---------|--------------------|-----------------------|
| LLM calls | 5 | 2 | 2 |
| EMB calls | 4 | 4 | 4 |
| VEC.search | 4 | 4 | 4 (but more precise) |
| Wall-clock (est.) | ~8s (concurrent) | ~5s | ~5s |
| LLM tokens (est.) | ~4000 | ~2500 | ~2800 |

The **batch decision** optimization alone cuts LLM calls by 60% and improves
quality. All other optimizations are additive.

---

## 3. Recommended Roadmap

| Phase | What | Quality Impact | Effort |
|-------|------|---------------|--------|
| **Phase 1** | Batch Decision | 🔴 High — global view, conflict resolution, -60% LLM calls | Medium |
| **Phase 2** | Structured Extraction (category + temporal) | 🟡 Medium — enables Phase 3 & 4 | Low-Medium |
| **Phase 3** | Search Enhancement (dynamic K + threshold + category filter) | 🟡 Medium — precision up | Low |
| **Phase 4** | Memory Lifecycle (time decay, confidence weighting, compaction) | 🟡 Medium — long-term quality | Medium-High |
| **Phase 5** | Hybrid Search (vector + keyword) | 🟠 Low-Medium — edge case improvement | Medium |

**Phase 1 is the clear first priority** — it simultaneously improves quality
(global decision coherence) and performance (fewer LLM calls).

---

## 4. Phase 1 Detailed Design Sketch: Batch Decision

### New Flow

```
add(messages, user_id)
│
├─ Phase A: Fact Extraction              1× LLM
│  └─ Extract [{text, confidence}, ...]
│
├─ Phase B: Parallel Embedding + Search  N× EMB + N× VEC.search (concurrent)
│  └─ For each fact:
│     ├─ fact_vector = embed(fact)
│     └─ similar = search(fact_vector)
│
├─ Phase C: Batch Decision               1× LLM
│  └─ LLM receives:
│     - ALL existing memories (deduplicated union of all search results)
│     - ALL new facts
│     - Decides action for EACH fact in one call
│
├─ Phase D: Execute Actions              writes (concurrent)
│  └─ For each decision:
│     └─ ADD / UPDATE / DELETE / NONE
│
└─ Return List[MemoryItem]
```

### Key Design Points

1. **Dedup search results**: Multiple facts may find the same existing memory.
   Deduplicate before sending to LLM to avoid confusion.

2. **Prompt size control**: If too many existing memories, truncate by
   relevance score. Set a `max_existing_memories` config.

3. **Fallback**: If batch response fails to parse, fall back to per-fact mode
   (current behavior). Never silently drop facts.

4. **Batch response schema**:
   ```json
   {
     "decisions": [
       {"fact_index": 0, "action": "NONE", "reason": "..."},
       {"fact_index": 1, "action": "UPDATE", "id": "2", "text": "...", "reason": "..."},
       {"fact_index": 2, "action": "ADD", "text": "...", "reason": "..."}
     ]
   }
   ```

5. **Concurrency model change**:
   - Current: facts go through full pipeline concurrently
   - New: embed+search concurrent (Phase B), decision serial (Phase C),
     execute concurrent (Phase D)
   - Net effect: still fast, because the LLM decision is now 1 call not N.
