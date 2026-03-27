"""Memory — the single entry point for the MIND memory system.

Usage::

    from mind import Memory

    m = Memory()                           # loads mind.toml defaults
    m.add(messages=[...], user_id="alice")

    # Override config at call time
    m.add(messages=[...], user_id="alice",
          overrides={"llm": {"model": "gpt-4o", "temperature": 0.3}})
"""

import json
import logging
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Any, Dict, List, Optional, Union
from pathlib import Path

from mind.config.manager import ConfigManager
from mind.config.models import MemoryItem, MemoryOperation, MemoryStatus
from mind.config.schema import LoggingConfig, MemoryConfig
from mind.embeddings.factory import EmbedderFactory
from mind.llms.factory import LlmFactory
from mind.prompts import (
    FACT_EXTRACTION_SYSTEM_PROMPT,
    FACT_EXTRACTION_USER_TEMPLATE,
    UPDATE_DECISION_SYSTEM_PROMPT,
    UPDATE_DECISION_USER_TEMPLATE,
    format_existing_memories,
)
from mind.ops_logger import ops
from mind.storage import SQLiteManager
from mind.utils import generate_hash, generate_id, get_utc_now, parse_messages
from mind.vector_stores.factory import VectorStoreFactory

logger = logging.getLogger(__name__)


class Memory:
    """MIND Memory — add, search, get, update, delete, and track history.

    Every public method accepts an optional ``overrides`` dict that is
    deep-merged on top of the base config for that single call. This
    allows upstream services to change model, temperature, provider, etc.
    on the fly without recreating the Memory instance.
    """

    def __init__(
        self,
        config: Optional[MemoryConfig] = None,
        toml_path: Optional[Union[str, Path]] = None,
    ) -> None:
        """Initialize the Memory system.

        Args:
            config: A pre-built MemoryConfig (e.g. from ConfigManager.get()).
                    If provided, toml_path is ignored.
            toml_path: Path to a TOML config file. Defaults to ``mind.toml``.
        """
        if config is not None:
            self._manager = ConfigManager.from_dict({})
            self._base_config = config
        else:
            self._manager = ConfigManager(toml_path)
            self._base_config = self._manager.get()

        # Set up logging based on config (only once per process)
        self._setup_logging(self._base_config.logging)

        # Infrastructure components (shared across calls, not LLM-dependent)
        self._vector_store = VectorStoreFactory.create(self._base_config.vector_store)
        self._history_store = SQLiteManager(self._base_config.history_store)
        self._vector_store.create_collection(self._base_config.embedding.dimensions)

        # ── Concurrency infrastructure ──
        cc = self._base_config.concurrency
        if cc.min_available_workers >= cc.max_workers:
            raise ValueError(
                f"min_available_workers ({cc.min_available_workers}) must be "
                f"strictly less than max_workers ({cc.max_workers})"
            )
        self._pool = ThreadPoolExecutor(
            max_workers=cc.max_workers,
            thread_name_prefix="mind-worker",
        )
        effective = cc.max_workers - cc.min_available_workers
        self._call_sem = threading.Semaphore(effective)

        logger.info(
            "Memory system initialized (pool=%d, sem=%d)",
            cc.max_workers, effective,
        )

    # ------------------------------------------------------------------
    # Logging setup
    # ------------------------------------------------------------------

    @staticmethod
    def _setup_logging(log_cfg: LoggingConfig) -> None:
        """Configure the ``mind`` package logger based on TOML config.

        Called once during Memory init. Subsequent calls are idempotent —
        handlers are only added if the root ``mind`` logger has none.
        """
        root_logger = logging.getLogger("mind")

        # Idempotent: skip if already configured
        if root_logger.handlers:
            return

        level = getattr(logging, log_cfg.level.upper(), logging.INFO)
        root_logger.setLevel(level)

        formatter = logging.Formatter(log_cfg.format)

        # Console handler (stderr)
        if log_cfg.console:
            console_handler = logging.StreamHandler(sys.stderr)
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)

        # File handler (optional)
        if log_cfg.file:
            file_handler = logging.FileHandler(log_cfg.file, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)

        # ── Configure centralised ops logger ──
        ops.configure(
            ops_llm=log_cfg.ops_llm,
            ops_vector_store=log_cfg.ops_vector_store,
            ops_database=log_cfg.ops_database,
            verbose=log_cfg.verbose,
        )

    # ------------------------------------------------------------------
    # Config resolution
    # ------------------------------------------------------------------

    def _resolve_config(self, overrides: Optional[Dict[str, Any]] = None) -> MemoryConfig:
        """Get the effective config for this call.

        If overrides is None, returns the base config (zero-cost).
        If overrides is provided, deep-merges on top and re-resolves.
        """
        if not overrides:
            return self._base_config
        return self._manager.get(overrides)

    def _make_llm(self, config: MemoryConfig):
        """Create an LLM client from the resolved config."""
        return LlmFactory.create(config.llm)

    def _make_embedder(self, config: MemoryConfig):
        """Create an Embedder client from the resolved config."""
        return EmbedderFactory.create(config.embedding)

    # ------------------------------------------------------------------
    # add
    # ------------------------------------------------------------------

    def add(
        self,
        messages: List[Dict[str, str]],
        user_id: str,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryItem]:
        """Extract facts from a conversation and store them as memories.

        Args:
            messages: Chat messages [{"role": ..., "content": ...}].
            user_id: The user this memory belongs to.
            session_id: Optional session identifier for source tracking.
            metadata: Optional extra metadata to attach.
            overrides: Optional config overrides for this call.

        Returns:
            List of MemoryItem objects that were created or updated.
        """
        config = self._resolve_config(overrides)
        llm = self._make_llm(config)
        embedder = self._make_embedder(config)

        conversation = parse_messages(messages)
        results: List[MemoryItem] = []

        # Step 1: Extract facts with confidence
        facts = self._extract_facts(llm, conversation)
        if not facts:
            logger.info("No facts extracted from conversation")
            return results

        logger.info("Extracted %d facts from conversation", len(facts))

        # Step 2: Process facts concurrently via the global thread pool.
        # Each fact is independent — no data dependency between facts.
        # The Semaphore prevents a single add() from monopolising the pool.
        valid_facts = [
            f for f in facts
            if f.get("text", "")
        ]

        def _guarded_process(fact: Dict[str, Any]) -> Optional[MemoryItem]:
            """Acquire semaphore, process one fact, release."""
            self._call_sem.acquire()
            try:
                return self._process_fact(
                    llm=llm, embedder=embedder, config=config,
                    fact_text=fact["text"],
                    confidence=fact.get("confidence", 0.5),
                    user_id=user_id, session_id=session_id,
                    source_context=conversation, metadata=metadata,
                )
            except Exception:
                logger.exception("Error processing fact: %s", fact["text"][:60])
                return None
            finally:
                self._call_sem.release()

        # Submit all facts to the pool; collect futures in order
        futures: List[Future] = [
            self._pool.submit(_guarded_process, f)
            for f in valid_facts
        ]

        # Gather results, preserving order, isolating per-fact errors
        for future in futures:
            try:
                item = future.result()
                if item is not None:
                    results.append(item)
            except Exception:
                # Should not happen — exceptions caught inside _guarded_process
                logger.exception("Unexpected error in fact processing future")

        return results

    # ------------------------------------------------------------------
    # search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        user_id: str,
        limit: Optional[int] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryItem]:
        """Search for memories relevant to the query.

        Args:
            query: The search query.
            user_id: Only return memories for this user.
            limit: Max results (defaults to config.retrieval.search_top_k).
            overrides: Optional config overrides for this call.
        """
        config = self._resolve_config(overrides)
        embedder = self._make_embedder(config)
        limit = limit or config.retrieval.search_top_k

        query_vector = embedder.embed(query)
        raw_results = self._vector_store.search(
            query_vector=query_vector, limit=limit,
            filters={"user_id": user_id, "status": MemoryStatus.ACTIVE.value},
        )

        items = []
        for r in raw_results:
            item = self._payload_to_item(r["id"], r.get("payload", {}))
            item.score = r.get("score")
            items.append(item)
        return items

    # ------------------------------------------------------------------
    # get / get_all
    # ------------------------------------------------------------------

    def get(self, memory_id: str) -> Optional[MemoryItem]:
        """Retrieve a single memory by ID."""
        record = self._vector_store.get(memory_id)
        if record is None:
            return None
        return self._payload_to_item(record["id"], record.get("payload", {}))

    def get_all(self, user_id: str, limit: int = 100) -> List[MemoryItem]:
        """Get all active memories for a user."""
        records = self._vector_store.list(
            filters={"user_id": user_id, "status": MemoryStatus.ACTIVE.value},
            limit=limit,
        )
        return [self._payload_to_item(r["id"], r.get("payload", {})) for r in records]

    # ------------------------------------------------------------------
    # update
    # ------------------------------------------------------------------

    def update(
        self,
        memory_id: str,
        content: str,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> Optional[MemoryItem]:
        """Manually update a memory's content (re-embeds)."""
        config = self._resolve_config(overrides)
        embedder = self._make_embedder(config)

        existing = self.get(memory_id)
        if existing is None:
            logger.warning("Memory %s not found for update", memory_id)
            return None

        old_content = existing.content
        new_vector = embedder.embed(content)
        now = get_utc_now()

        self._vector_store.update(
            id=memory_id, vector=new_vector,
            payload={"content": content, "hash": generate_hash(content),
                     "updated_at": now.isoformat()},
        )
        self._history_store.add_record(
            memory_id=memory_id, user_id=existing.user_id,
            operation=MemoryOperation.UPDATE,
            old_content=old_content, new_content=content,
        )
        return self.get(memory_id)

    # ------------------------------------------------------------------
    # delete
    # ------------------------------------------------------------------

    def delete(self, memory_id: str) -> bool:
        """Logically delete a memory (status → deleted)."""
        existing = self.get(memory_id)
        if existing is None:
            logger.warning("Memory %s not found for delete", memory_id)
            return False

        now = get_utc_now()
        self._vector_store.update(
            id=memory_id,
            payload={"status": MemoryStatus.DELETED.value, "updated_at": now.isoformat()},
        )
        self._history_store.add_record(
            memory_id=memory_id, user_id=existing.user_id,
            operation=MemoryOperation.DELETE, old_content=existing.content,
        )
        logger.info("Deleted memory %s", memory_id)
        return True

    # ------------------------------------------------------------------
    # history
    # ------------------------------------------------------------------

    def history(self, memory_id: str) -> List[Dict[str, Any]]:
        """Get the operation history for a memory."""
        records = self._history_store.get_history(memory_id)
        return [r.model_dump() for r in records]

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Shut down the thread pool and release resources.

        Waits for all in-flight fact-processing tasks to finish before
        returning.  Safe to call multiple times.
        """
        self._pool.shutdown(wait=True)
        self._history_store.close()
        logger.info("Memory system shut down")

    # ==================================================================
    # Internal methods
    # ==================================================================

    def _extract_facts(self, llm, conversation: str) -> List[Dict[str, Any]]:
        messages = [
            {"role": "system", "content": FACT_EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": FACT_EXTRACTION_USER_TEMPLATE.format(
                conversation=conversation)},
        ]
        response = llm.generate(
            messages=messages,
            response_format={"type": "json_object"},
            prompt_name="FACT_EXTRACTION",
        )
        try:
            return json.loads(response).get("facts", [])
        except json.JSONDecodeError:
            logger.error("Failed to parse fact extraction response: %s", response)
            return []

    def _process_fact(
        self, llm, embedder, config: MemoryConfig,
        fact_text: str, confidence: float, user_id: str,
        session_id: Optional[str], source_context: str,
        metadata: Optional[Dict[str, Any]],
    ) -> Optional[MemoryItem]:
        fact_vector = embedder.embed(fact_text)

        similar = self._vector_store.search(
            query_vector=fact_vector,
            limit=config.retrieval.similarity_top_k,
            filters={"user_id": user_id, "status": MemoryStatus.ACTIVE.value},
        )

        temp_to_real = {}
        memory_list = []
        for idx, s in enumerate(similar):
            temp_to_real[str(idx)] = s["id"]
            memory_list.append({"content": s.get("payload", {}).get("content", "")})

        existing_text = format_existing_memories(memory_list)
        decision_messages = [
            {"role": "system", "content": UPDATE_DECISION_SYSTEM_PROMPT},
            {"role": "user", "content": UPDATE_DECISION_USER_TEMPLATE.format(
                existing_memories=existing_text, new_fact=fact_text)},
        ]
        decision_response = llm.generate(
            messages=decision_messages,
            response_format={"type": "json_object"},
            prompt_name="UPDATE_DECISION",
        )

        try:
            decision = json.loads(decision_response)
        except json.JSONDecodeError:
            logger.error("Failed to parse update decision: %s", decision_response)
            return None

        action = decision.get("action", "NONE").upper()
        reason = decision.get("reason", "")
        logger.info("Fact: '%s' → Decision: %s (reason: %s)", fact_text[:60], action, reason)

        if action == "ADD":
            return self._execute_add(
                embedder=embedder, text=decision.get("text", fact_text),
                vector=fact_vector, confidence=confidence, user_id=user_id,
                session_id=session_id, source_context=source_context, metadata=metadata)
        elif action == "UPDATE":
            temp_id = str(decision.get("id", ""))
            real_id = temp_to_real.get(temp_id)
            if real_id is None:
                logger.warning("UPDATE referenced invalid ID: %s — falling back to ADD", temp_id)
                return self._execute_add(
                    embedder=embedder, text=decision.get("text", fact_text),
                    vector=fact_vector, confidence=confidence, user_id=user_id,
                    session_id=session_id, source_context=source_context, metadata=metadata)
            return self._execute_update(
                embedder=embedder, old_memory_id=real_id,
                new_text=decision.get("text", fact_text), confidence=confidence,
                user_id=user_id, session_id=session_id,
                source_context=source_context, metadata=metadata)
        elif action == "DELETE":
            temp_id = str(decision.get("id", ""))
            real_id = temp_to_real.get(temp_id)
            if real_id:
                self.delete(real_id)
            return None
        else:
            logger.debug("No action for fact: %s", fact_text[:60])
            return None

    def _execute_add(
        self, embedder, text: str, vector: List[float], confidence: float,
        user_id: str, session_id: Optional[str], source_context: str,
        metadata: Optional[Dict[str, Any]],
    ) -> MemoryItem:
        now = get_utc_now()
        memory_id = generate_id()
        payload = {
            "user_id": user_id, "content": text, "hash": generate_hash(text),
            "metadata": metadata or {}, "created_at": now.isoformat(),
            "updated_at": now.isoformat(), "confidence": confidence,
            "status": MemoryStatus.ACTIVE.value, "source_context": source_context,
            "source_session_id": session_id, "version_of": None,
        }
        self._vector_store.insert(id=memory_id, vector=vector, payload=payload)
        self._history_store.add_record(
            memory_id=memory_id, user_id=user_id,
            operation=MemoryOperation.ADD, new_content=text)
        logger.info("Added memory %s: %s", memory_id, text[:60])
        return self._payload_to_item(memory_id, payload)

    def _execute_update(
        self, embedder, old_memory_id: str, new_text: str,
        confidence: float, user_id: str, session_id: Optional[str],
        source_context: str, metadata: Optional[Dict[str, Any]],
    ) -> MemoryItem:
        old_memory = self.get(old_memory_id)
        old_content = old_memory.content if old_memory else None

        new_vector = embedder.embed(new_text)
        now = get_utc_now()
        new_memory_id = generate_id()
        payload = {
            "user_id": user_id, "content": new_text, "hash": generate_hash(new_text),
            "metadata": metadata or {}, "created_at": now.isoformat(),
            "updated_at": now.isoformat(), "confidence": confidence,
            "status": MemoryStatus.ACTIVE.value, "source_context": source_context,
            "source_session_id": session_id, "version_of": old_memory_id,
        }
        self._vector_store.insert(id=new_memory_id, vector=new_vector, payload=payload)
        self._history_store.add_record(
            memory_id=new_memory_id, user_id=user_id,
            operation=MemoryOperation.ADD, new_content=new_text,
            metadata={"version_of": old_memory_id})
        self._history_store.add_record(
            memory_id=old_memory_id, user_id=user_id,
            operation=MemoryOperation.UPDATE, old_content=old_content,
            new_content=new_text, metadata={"superseded_by": new_memory_id})
        logger.info("Updated: %s → %s (version_of=%s)", old_memory_id, new_memory_id, old_memory_id)
        return self._payload_to_item(new_memory_id, payload)

    @staticmethod
    def _payload_to_item(memory_id: str, payload: Dict[str, Any]) -> MemoryItem:
        return MemoryItem(
            id=memory_id, user_id=payload.get("user_id", ""),
            content=payload.get("content", ""), hash=payload.get("hash", ""),
            metadata=payload.get("metadata", {}),
            created_at=payload.get("created_at"), updated_at=payload.get("updated_at"),
            confidence=payload.get("confidence"),
            status=MemoryStatus(payload.get("status", "active")),
            source_context=payload.get("source_context"),
            source_session_id=payload.get("source_session_id"),
            version_of=payload.get("version_of"),
            importance=payload.get("importance"), type=payload.get("type"),
        )