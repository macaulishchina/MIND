# Change Proposal: Logging System Refactor

## Metadata

- Change ID: `logging-refactor`
- Type: `refactor` + `feature`
- Status: `draft`
- Spec impact: Config schema change (additive)
- Owner: `agent`

## Summary

The current logging system suffers from **shotgun surgery** — ops logging
logic is scattered across 4 base modules, each with its own `_ops_log_enabled`
global variable, hardcoded emoji formats, and no verbose mode. Adding a new
component requires changes in 3+ places.

This refactor introduces a **centralized `OpsLogger`** module that:
1. Owns all ops logging configuration (switches, verbose mode)
2. Provides typed methods for each component (LLM, EMB, VEC, DB)
3. Handles both summary and verbose formatting
4. Is configured once by `Memory._setup_logging()`

## Current Problems

| Problem | Location | Impact |
|---------|----------|--------|
| 4 scattered `_ops_log_enabled` globals | llms/base, embeddings/base, vector_stores/base, storage | Shotgun surgery for any logging change |
| `memory.py` imports 4 modules to set globals | memory.py:139-143 | Tight coupling, fragile |
| Hardcoded emoji/format in each base class | 6+ log format strings | Inconsistent, hard to change style |
| No verbose mode | everywhere | Can't debug input/output content |
| `storage.py` has duplicated code | lines 175-344 | Copy-paste artifact |
| Adding a new component = 3 places to change | schema + base + memory | Error-prone |

## Proposed Architecture

```
┌─────────────────────────────────────────────────┐
│  mind.toml                                      │
│  [logging]                                      │
│  ops_llm = true                                 │
│  ops_vector_store = true                        │
│  ops_database = true                            │
│  verbose = false          ← NEW                 │
└───────────────┬─────────────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────────────┐
│  mind/ops_logger.py  (NEW — centralized)        │
│                                                 │
│  class OpsLogger:                               │
│      # ── state ──                              │
│      ops_llm: bool                              │
│      ops_vector_store: bool                     │
│      ops_database: bool                         │
│      verbose: bool                              │
│                                                 │
│      # ── public API ──                         │
│      def llm_call(provider, model, msgs,        │
│                   in_tok, out_tok, elapsed,      │
│                   messages=None, response=None)  │
│      def llm_error(...)                         │
│      def emb_call(provider, model, text_len,    │
│                   dim, elapsed,                  │
│                   input_text=None, vector=None)  │
│      def emb_error(...)                         │
│      def vec_op(op, collection, url, elapsed,   │
│                 detail=None,                     │
│                 payload=None, results=None)      │
│      def vec_error(...)                         │
│      def db_op(op, table, db_path, elapsed,     │
│                detail=None,                      │
│                record=None, results=None)        │
│      def db_error(...)                          │
│                                                 │
│  # Module-level singleton                       │
│  ops = OpsLogger()                              │
└───────────────┬─────────────────────────────────┘
                │
    ┌───────────┼───────────┬───────────┐
    ▼           ▼           ▼           ▼
 BaseLLM   BaseEmbedding  BaseVec    SQLiteMgr
 calls     calls          calls      calls
 ops.llm_call()  ops.emb_call()  ops.vec_op()  ops.db_op()
```

### Key Design Points

**1. OpsLogger is a plain class, not a Python logger**

It *uses* `logging.getLogger("mind.ops")` internally, but the public API is
typed methods — not raw `logger.info()` calls. This gives us:
- Type safety (IDE autocomplete, no format string bugs)
- Centralized formatting decisions
- Easy to add verbose content without touching callers

**2. Summary vs Verbose output**

```python
# Summary (always, when ops switch is on):
🧠 [LLM] ── deepseek | deepseek-chat | 2 msgs | ~405 in_tok | ~71 out_tok | 4.61s ──

# Verbose (only when verbose=True, logged at DEBUG level):
🧠 [LLM] ── deepseek | deepseek-chat | 2 msgs | ~405 in_tok | ~71 out_tok | 4.61s ──
   ┊ input[0] system: You are a memory extraction assistant. Your job is to extract factual
   ┊          information from conversations that would be useful to remember...
   ┊ input[1] user: Extract the key facts from the following conversation...
   ┊ output: {"facts": [{"text": "The user's name is Zhang San.", "confidence": 1.0}, ...]}
```

Verbose format principles:
- **Indented with `┊`** — visually nested under the summary line
- **Truncated** — long content capped at configurable max chars (default 500)
- **LLM**: show each message role + content preview, show response
- **EMB**: show input text, show vector[:5] + `...` (first 5 dims)
- **VEC**: show payload/results as compact JSON
- **DB**: show record content

**3. Error logs are always emitted** — not gated by ops switches

**4. Configuration**

```toml
[logging]
level   = "INFO"
console = true
file    = ""
format  = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"

# ── ops logging ──
ops_llm          = true     # 🧠 LLM + 🔗 Embedding
ops_vector_store = true     # 📦 Vector store
ops_database     = true     # 💾 Database
verbose          = false    # Detailed input/output content (DEBUG level)
```

`verbose` requires the logging `level` to be `DEBUG` or a special handling
(we log verbose lines at INFO level but with the `┊` prefix so they're
visually subordinate). **Decision: verbose logs at INFO level** so users
don't have to change `level` just to see verbose output.

## Changes Required

### New Files

| File | Description |
|------|-------------|
| `mind/ops_logger.py` | Centralized OpsLogger class + module singleton |

### Modified Files

| File | Change |
|------|--------|
| `mind/config/schema.py` | Add `verbose: bool = False` to LoggingConfig |
| `mind.toml.example` | Add `verbose = false` example |
| `mind/llms/base.py` | Remove `_ops_log_enabled`, import & call `ops.llm_call()` |
| `mind/embeddings/base.py` | Remove `_ops_log_enabled`, import & call `ops.emb_call()` |
| `mind/vector_stores/base.py` | Remove `_ops_log_enabled`, import & call `ops.vec_op()` |
| `mind/storage.py` | Remove `_ops_log_enabled`, remove duplicate code, import & call `ops.db_op()` |
| `mind/memory.py` | Remove 4-module import hack, configure `ops` singleton instead |

### Deleted Patterns

- All `_ops_log_enabled: bool = True` module globals (4 occurrences)
- All `if _ops_log_enabled:` guards (8+ occurrences)
- All hardcoded emoji format strings in base classes
- `memory.py` lines 139-143 (direct module variable setting)
- `storage.py` lines 175-344 (duplicated code)

## OpsLogger API Design

```python
"""mind/ops_logger.py — Centralized operations logger."""

import logging
import json
from typing import Any, Dict, List, Optional

logger = logging.getLogger("mind.ops")

_MAX_VERBOSE_CHARS = 500  # Truncation limit for verbose content


def _truncate(text: str, max_len: int = _MAX_VERBOSE_CHARS) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"... ({len(text)} chars total)"


def _indent(text: str, prefix: str = "   ┊ ") -> str:
    return "\n".join(prefix + line for line in text.split("\n"))


class OpsLogger:
    """Centralized operations logger for MIND components."""

    def __init__(self) -> None:
        self.ops_llm: bool = True
        self.ops_vector_store: bool = True
        self.ops_database: bool = True
        self.verbose: bool = False

    def configure(self, ops_llm, ops_vector_store, ops_database, verbose):
        """Called once by Memory._setup_logging()."""
        self.ops_llm = ops_llm
        self.ops_vector_store = ops_vector_store
        self.ops_database = ops_database
        self.verbose = verbose

    # ── LLM ──

    def llm_call(self, provider, model, n_msgs, in_tok, out_tok, elapsed,
                 *, messages=None, response=None):
        if not self.ops_llm:
            return
        summary = (
            f"🧠 [LLM] ── {provider} | {model} | "
            f"{n_msgs} msgs | ~{in_tok} in_tok | ~{out_tok} out_tok | "
            f"{elapsed:.2f}s ──"
        )
        logger.info(summary)
        if self.verbose and (messages or response):
            self._verbose_llm(messages, response)

    def llm_error(self, provider, model, n_msgs, in_tok, elapsed):
        # Always emit — not gated by ops switch
        logger.error(
            "🧠 [LLM] ── %s | %s | %d msgs | ~%d in_tok | FAILED | %.2fs ──",
            provider, model, n_msgs, in_tok, elapsed,
        )

    def _verbose_llm(self, messages, response):
        lines = []
        if messages:
            for i, m in enumerate(messages):
                role = m.get("role", "?")
                content = _truncate(m.get("content", ""))
                lines.append(f"input[{i}] {role}: {content}")
        if response:
            lines.append(f"output: {_truncate(response)}")
        if lines:
            logger.info(_indent("\n".join(lines)))

    # ── Embedding ──

    def emb_call(self, provider, model, text_len, dim, elapsed,
                 *, input_text=None, vector=None):
        if not self.ops_llm:  # shares LLM switch
            return
        summary = (
            f"🔗 [EMB] ── {provider} | {model} | "
            f"{text_len} chars | dim={dim} | {elapsed:.2f}s ──"
        )
        logger.info(summary)
        if self.verbose and (input_text or vector):
            self._verbose_emb(input_text, vector)

    def emb_error(self, provider, model, text_len, elapsed):
        logger.error(
            "🔗 [EMB] ── %s | %s | %d chars | FAILED | %.2fs ──",
            provider, model, text_len, elapsed,
        )

    def _verbose_emb(self, input_text, vector):
        lines = []
        if input_text:
            lines.append(f"input: {_truncate(input_text)}")
        if vector:
            preview = vector[:5]
            lines.append(f"output: [{', '.join(f'{v:.4f}' for v in preview)}, ...] dim={len(vector)}")
        if lines:
            logger.info(_indent("\n".join(lines)))

    # ── Vector Store ──

    def vec_op(self, op, collection, url, elapsed, *,
               detail="", payload=None, results=None):
        if not self.ops_vector_store:
            return
        parts = [f"📦 [VEC] ── {op} | {collection} @ {url}"]
        if detail:
            parts.append(f" | {detail}")
        parts.append(f" | {elapsed:.3f}s ──")
        logger.info("".join(parts))
        if self.verbose and (payload or results):
            self._verbose_vec(op, payload, results)

    def vec_error(self, op, collection, url, elapsed, *, detail=""):
        parts = [f"📦 [VEC] ── {op} | {collection} @ {url}"]
        if detail:
            parts.append(f" | {detail}")
        parts.append(f" | FAILED | {elapsed:.3f}s ──")
        logger.error("".join(parts))

    def _verbose_vec(self, op, payload, results):
        lines = []
        if payload:
            lines.append(f"payload: {_truncate(json.dumps(payload, ensure_ascii=False, default=str))}")
        if results:
            if isinstance(results, list):
                lines.append(f"results: {len(results)} items")
                for i, r in enumerate(results[:3]):  # show first 3
                    lines.append(f"  [{i}] {_truncate(json.dumps(r, ensure_ascii=False, default=str), 200)}")
                if len(results) > 3:
                    lines.append(f"  ... and {len(results) - 3} more")
            else:
                lines.append(f"result: {_truncate(json.dumps(results, ensure_ascii=False, default=str))}")
        if lines:
            logger.info(_indent("\n".join(lines)))

    # ── Database ──

    def db_op(self, op, table, db_path, elapsed, *,
              detail="", record=None, results=None):
        if not self.ops_database:
            return
        parts = [f"💾 [DB] ── {op} | {table} @ {db_path}"]
        if detail:
            parts.append(f" | {detail}")
        parts.append(f" | {elapsed:.3f}s ──")
        logger.info("".join(parts))
        if self.verbose and (record or results):
            self._verbose_db(op, record, results)

    def db_error(self, op, table, db_path, elapsed, *, detail=""):
        parts = [f"💾 [DB] ── {op} | {table} @ {db_path}"]
        if detail:
            parts.append(f" | {detail}")
        parts.append(f" | FAILED | {elapsed:.3f}s ──")
        logger.error("".join(parts))

    def _verbose_db(self, op, record, results):
        lines = []
        if record:
            lines.append(f"record: {_truncate(json.dumps(record, ensure_ascii=False, default=str))}")
        if results:
            if isinstance(results, list):
                lines.append(f"results: {len(results)} rows")
                for i, r in enumerate(results[:3]):
                    lines.append(f"  [{i}] {_truncate(str(r), 200)}")
                if len(results) > 3:
                    lines.append(f"  ... and {len(results) - 3} more")
        if lines:
            logger.info(_indent("\n".join(lines)))


# Module-level singleton
ops = OpsLogger()
```

## Caller-Side Changes (Before → After)

### BaseLLM.generate() — Before:
```python
from mind.llms import base as _llm_base
# in base.py:
_ops_log_enabled: bool = True
...
if _ops_log_enabled:
    logger.info("🧠 [LLM] ── %s | %s | ...", provider, model, ...)
```

### BaseLLM.generate() — After:
```python
from mind.ops_logger import ops
...
ops.llm_call(provider, model, n_msgs, in_tok, out_tok, elapsed,
             messages=messages, response=result)
```

## Verbose Output Examples

### LLM (verbose=true)
```
🧠 [LLM] ── deepseek | deepseek-chat | 2 msgs | ~405 in_tok | ~71 out_tok | 4.61s ──
   ┊ input[0] system: You are a memory extraction assistant. Your job is to extract factual
   ┊          information from conversations that would be useful to remember...
   ┊ input[1] user: Extract the key facts from the following conversation...
   ┊ output: {"facts": [{"text": "The user's name is Zhang San.", "confidence": 1.0}, ...]}
```

### Embedding (verbose=true)
```
🔗 [EMB] ── openai-embedding | text-embedding-v4 | 29 chars | dim=1024 | 0.31s ──
   ┊ input: The user's name is Zhang San.
   ┊ output: [0.0123, -0.0456, 0.0789, 0.0012, -0.0345, ...] dim=1024
```

### Vector Store (verbose=true)
```
📦 [VEC] ── SEARCH | mind_memories @ :memory: | limit=5 | hits=4 | 0.014s ──
   ┊ results: 4 items
   ┊   [0] {"id": "abc123", "score": 0.95, "payload": {"content": "用户叫张三"}}
   ┊   [1] {"id": "def456", "score": 0.87, "payload": {"content": "用户28岁"}}
   ┊   [2] {"id": "ghi789", "score": 0.82, "payload": {"content": "用户在网易工作"}}
   ┊   ... and 1 more
```

### Database (verbose=true)
```
💾 [DB] ── INSERT | memory_history @ mind_history.db | ADD | mem=abc123 | 0.002s ──
   ┊ record: {"id": "rec001", "memory_id": "abc123", "operation": "ADD", "new_content": "用户叫张三"}
```

## Acceptance Signals

1. All `_ops_log_enabled` module globals removed (0 occurrences)
2. All ops log formatting centralized in `ops_logger.py`
3. `storage.py` duplicate code removed
4. `verbose=false` (default) produces identical output to current system
5. `verbose=true` shows detailed input/output for all 4 component types
6. Adding a new ops log category requires only: 1 method in OpsLogger + 1 call site
7. Existing tests pass

## Approval

- [ ] Proposal reviewed
- [ ] Ready to implement
