"""Memory — the single entry point for the MIND memory system.

Usage::

    from mind import Memory

    m = Memory()                           # loads mind.toml defaults
    m.add(messages=[...], user_id="alice")

    # Override config at construction time
    m = Memory(overrides={"llm": {"model": "gpt-4o", "temperature": 0.3}})
"""

import json
import logging
import re
import sys
import time
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Union
from pathlib import Path

from mind.config.manager import ConfigManager
from mind.config.models import (
    FactEnvelope,
    FactFamily,
    MemoryItem,
    MemoryOperation,
    MemoryStatus,
    OwnerContext,
    OwnerRecord,
)
from mind.config.schema import LoggingConfig, MemoryConfig
from mind.embeddings.factory import EmbedderFactory
from mind.llms.factory import LlmFactory
from mind.prompts import (
    UPDATE_DECISION_SYSTEM_PROMPT,
    UPDATE_DECISION_USER_TEMPLATE,
    format_existing_memories,
)
from mind.ops_logger import ops
from mind.stl.focus import FocusStack
from mind.stl.parser import parse_program
from mind.stl.prompt import (
    STL_EXTRACTION_SYSTEM_PROMPT,
    STL_EXTRACTION_USER_TEMPLATE,
    format_focus_stack,
)
from mind.stl.store import STLStoreFactory
from datetime import date as _date
from mind.storage import HistoryStoreFactory
from mind.utils import generate_hash, generate_id, get_utc_now, parse_messages
from mind.vector_stores.factory import VectorStoreFactory

logger = logging.getLogger(__name__)

_SINGLE_VALUE_FIELDS = {
    "name",
    "age",
    "occupation",
    "location",
    "workplace",
    "language",
    "relation_to_owner",
}
_SET_VALUE_FAMILIES = {
    FactFamily.PREFERENCE,
    FactFamily.BELIEF,
    FactFamily.HABIT,
}
_APPEND_ONLY_FAMILIES = {
    FactFamily.EVENT,
    FactFamily.PLAN,
    FactFamily.QUOTE,
}
_OWNER_RELATION_PREDICATES = {
    "friend",
    "mother",
    "father",
    "spouse",
    "partner",
    "child",
    "coworker",
    "boss",
    "mentor",
    "student",
    "roommate",
    "neighbor",
    "classmate",
    "teammate",
    "client",
    "landlord",
    "doctor",
    "pet",
}


class Memory:
    """MIND Memory — add, search, get, update, delete, and track history.

    All configuration and dependency objects (LLM client, embedder, vector
    store, etc.) are resolved once at construction time and shared across
    all subsequent method calls.  To use different settings, create a new
    ``Memory`` instance.
    """

    def __init__(
        self,
        config: Optional[MemoryConfig] = None,
        toml_path: Optional[Union[str, Path]] = None,
        overrides: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize the Memory system.

        Args:
            config: A pre-built MemoryConfig (e.g. from ConfigManager.get()).
                    If provided, *toml_path* and *overrides* are ignored.
            toml_path: Path to a TOML config file. Defaults to ``mind.toml``.
            overrides: Optional config overrides deep-merged on top of the
                       TOML config at construction time.
        """
        if config is not None:
            self._config = config
        else:
            manager = ConfigManager(toml_path)
            self._config = manager.get(overrides)

        # Set up logging based on config (only once per process)
        self._setup_logging(self._config.logging)

        # ── Dependency objects (fixed for the lifetime of this instance) ──
        self.llm = LlmFactory.create(self._config.llm)
        self.decision_llm = LlmFactory.create(
            self._config.llm_stages.get("decision", self._config.llm)
        )
        self.embedder = EmbedderFactory.create(self._config.embedding)
        self._vector_store = VectorStoreFactory.create(self._config.vector_store)
        self._history_store = HistoryStoreFactory.create(self._config.history_store)
        self._stl_store = STLStoreFactory.create(self._config.stl_store)
        self._vector_store.create_collection(self._config.embedding.dimensions)
        self.stl_extraction_llm = LlmFactory.create(
            self._config.llm_stages.get("stl_extraction", self._config.llm)
        )

        # ── Concurrency infrastructure ──
        cc = self._config.concurrency
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

    # ══════════════════════════════════════════════════════════════════
    # Bootstrap (logging)
    # ══════════════════════════════════════════════════════════════════

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

    # ══════════════════════════════════════════════════════════════════
    # Public interface
    # ══════════════════════════════════════════════════════════════════

    def add(
        self,
        messages: List[Dict[str, str]],
        user_id: Optional[str] = None,
        owner: Optional[OwnerContext] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[MemoryItem]:
        """Extract facts from a conversation and store them as memories.

        Uses the Semantic Translation Layer (STL) pipeline:
        1. Single LLM call → structured STL output
        2. Deterministic parser → ParsedProgram
        3. Batch relational persist → STL store
        4. Embed each statement for vector search

        Args:
            messages: Chat messages [{"role": ..., "content": ...}].
            user_id: Backward-compatible alias for ``owner.external_user_id``.
            owner: Structured owner identity.
            session_id: Optional session identifier for source tracking.
            metadata: Optional extra metadata to attach.

        Returns:
            List of MemoryItem objects that were created.
        """
        conversation = parse_messages(messages)
        owner_context = self._coerce_owner_context(user_id=user_id, owner=owner)
        owner_record = self._history_store.resolve_owner(owner_context)
        owner_user_id = self._owner_user_id(owner_record)

        add_t0 = time.perf_counter()
        n_msgs = len(messages)
        logger.info("📝 [ADD] ── START | owner=%s | %d messages ──", owner_user_id, n_msgs)

        # ── Step 1: Single LLM extraction ──
        stl_text = self._extract_stl(
            conversation,
            owner_id=owner_record.owner_id,
            current_turn=len(messages),
        )
        if not stl_text.strip():
            elapsed = time.perf_counter() - add_t0
            logger.info(
                "📝 [ADD] ── DONE | owner=%s | empty STL output | %.2fs ──",
                owner_user_id, elapsed,
            )
            return []

        # ── Step 2: Parse ──
        program = parse_program(stl_text, batch_id=generate_id())
        if not program.statements and not program.evidence:
            elapsed = time.perf_counter() - add_t0
            logger.info(
                "📝 [ADD] ── DONE | owner=%s | 0 statements parsed | %.2fs ──",
                owner_user_id, elapsed,
            )
            return []

        logger.info(
            "Parsed %d refs, %d statements, %d evidence, %d notes (%d failed)",
            len(program.refs),
            len(program.statements),
            len(program.evidence),
            len(program.notes),
            len(program.failed_lines),
        )

        # ── Step 3: Persist to STL relational store ──
        conv_id = session_id or generate_id()
        self._stl_store.create_conversation(conv_id)
        storage_result = self._stl_store.store_program(
            program=program,
            owner_id=owner_record.owner_id,
            conv_id=conv_id,
            model=self.stl_extraction_llm.model if hasattr(self.stl_extraction_llm, "model") else None,
            embedder=self.embedder,
            anchor_date=_date.today(),
        )

        logger.info(
            "STL stored: %d refs, %d stmts, %d ev, %d notes, %d errors",
            storage_result.refs_upserted,
            storage_result.statements_inserted,
            storage_result.evidence_inserted,
            storage_result.notes_inserted,
            len(storage_result.errors),
        )

        # ── Step 4: Project statements into owner-centered memories ──
        results: List[MemoryItem] = []
        relation_subject_cache = self._build_relation_subject_cache(
            program=program,
            owner_record=owner_record,
        )
        for stmt in program.statements:
            envelope = self._statement_to_envelope(
                stmt=stmt,
                program=program,
                owner_record=owner_record,
                session_id=session_id,
                source_context=conversation,
                metadata=metadata,
                relation_subject_cache=relation_subject_cache,
            )
            if envelope is None:
                continue
            try:
                item = self._process_envelope(envelope)
                if item is not None:
                    results.append(item)
            except Exception:
                logger.exception("Failed to project/store statement $%s", stmt.local_id)

        elapsed = time.perf_counter() - add_t0
        logger.info(
            "📝 [ADD] ── DONE | owner=%s | %d stmts | %d projected | %.2fs ──",
            owner_user_id, len(program.statements), len(results), elapsed,
        )
        return results

    def _build_relation_subject_cache(
        self,
        program,
        owner_record: OwnerRecord,
    ) -> Dict[str, Dict[str, str]]:
        """Resolve stable owner-local subject refs for relation targets in one batch."""
        ref_map = {ref.local_id: ref.expr for ref in program.refs}
        cache: Dict[str, Dict[str, str]] = {}

        for stmt in program.statements:
            if stmt.predicate not in _OWNER_RELATION_PREDICATES or len(stmt.args) < 2:
                continue
            first_arg, second_arg = stmt.args[0], stmt.args[1]
            if getattr(first_arg, "kind", None) != "ref" or first_arg.ref_id not in {"s", "self"}:
                continue
            if getattr(second_arg, "kind", None) != "ref":
                continue
            target_ref_id = second_arg.ref_id
            if target_ref_id in cache:
                continue

            relation_type = self._normalize_relation_type(stmt.predicate)
            expr = ref_map.get(target_ref_id)
            scope = getattr(getattr(expr, "scope", None), "value", getattr(expr, "scope", None))

            if expr is not None and expr.key and scope != "blank":
                subject = self._history_store.get_or_create_named_subject(
                    owner_id=owner_record.owner_id,
                    relation_type=relation_type,
                    display_name=expr.key,
                    normalized_name=self._normalize_name(expr.key),
                    aliases={"stl_ref_id": target_ref_id},
                )
            else:
                subject = self._history_store.create_placeholder_subject(
                    owner_id=owner_record.owner_id,
                    relation_type=relation_type,
                    aliases={"stl_ref_id": target_ref_id},
                )

            cache[target_ref_id] = {
                "subject_ref": subject.subject_ref,
                "relation_type": relation_type,
            }

        return cache

    def search(
        self,
        query: str,
        user_id: str,
        limit: Optional[int] = None,
    ) -> List[MemoryItem]:
        """Search for memories relevant to the query.

        Executes a hybrid search:
        1. Vector similarity search (existing, always runs)
        2. STL structured query (predicate/ref-based, when applicable)

        Args:
            query: The search query.
            user_id: Only return memories for this user.
            limit: Max results (defaults to config.retrieval.search_top_k).
        """
        limit = limit or self._config.retrieval.search_top_k

        # ── Vector search ──
        query_vector = self.embedder.embed(query)
        raw_results = self._vector_store.search(
            query_vector=query_vector, limit=limit,
            filters={"user_id": user_id, "status": MemoryStatus.ACTIVE.value},
        )

        items = []
        seen_ids = set()
        for r in raw_results:
            item = self._payload_to_item(r["id"], r.get("payload", {}))
            item.score = r.get("score")
            items.append(item)
            seen_ids.add(r["id"])

        # ── Structured STL search (supplement) ──
        try:
            owner_ctx = self._coerce_owner_context(user_id=user_id, owner=None)
            owner_record = self._history_store.resolve_owner(owner_ctx)
            stl_rows = self._stl_store.query_statements(
                owner_id=owner_record.owner_id,
                limit=limit,
            )
            for row in stl_rows:
                stmt_id = row.get("id", "")
                if stmt_id in seen_ids:
                    continue
                # Convert STL row to MemoryItem for a unified response
                import json as _json
                args = row.get("args", [])
                if isinstance(args, str):
                    args = _json.loads(args)
                canonical = f"{row.get('predicate', '')}({', '.join(str(a) for a in args)})"
                item = MemoryItem(
                    id=stmt_id,
                    user_id=user_id,
                    owner_id=row.get("owner_id"),
                    content=canonical,
                    hash=generate_hash(canonical),
                    created_at=row.get("created_at"),
                    updated_at=row.get("created_at"),
                    status=MemoryStatus.ACTIVE,
                    canonical_text=canonical,
                )
                items.append(item)
                seen_ids.add(stmt_id)
        except Exception:
            logger.debug("STL structured search supplement failed", exc_info=True)

        return items[:limit]

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

    def update(
        self,
        memory_id: str,
        content: str,
    ) -> Optional[MemoryItem]:
        """Manually update a memory's content (re-embeds)."""
        existing = self.get(memory_id)
        if existing is None:
            logger.warning("Memory %s not found for update", memory_id)
            return None

        old_content = existing.content
        new_vector = self.embedder.embed(content)
        now = get_utc_now()

        self._vector_store.update(
            id=memory_id, vector=new_vector,
            payload={
                "content": content,
                "canonical_text": content,
                "raw_text": content,
                "field_value_json": {"value": content},
                "hash": generate_hash(content),
                "updated_at": now.isoformat(),
            },
        )
        self._history_store.add_record(
            memory_id=memory_id, user_id=existing.user_id,
            operation=MemoryOperation.UPDATE,
            old_content=old_content, new_content=content,
        )
        return self.get(memory_id)

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
            metadata={
                "owner_id": existing.owner_id,
                "subject_ref": existing.subject_ref,
                "fact_family": (
                    existing.fact_family.value
                    if existing.fact_family is not None
                    else None
                ),
                "field_key": existing.field_key,
                "canonical_text": existing.canonical_text or existing.content,
            },
        )
        logger.info("Deleted memory %s", memory_id)
        return True

    def history(self, memory_id: str) -> List[Dict[str, Any]]:
        """Get the operation history for a memory."""
        records = self._history_store.get_history(memory_id)
        return [r.model_dump() for r in records]

    def close(self) -> None:
        """Shut down the thread pool and release resources.

        Waits for all in-flight fact-processing tasks to finish before
        returning.  Safe to call multiple times.
        """
        self._pool.shutdown(wait=True)
        self._history_store.close()
        self._stl_store.close()
        logger.info("Memory system shut down")

    # ══════════════════════════════════════════════════════════════════
    # Core capabilities (each independently callable and testable)
    # ══════════════════════════════════════════════════════════════════

    @staticmethod
    def _normalize_fact_text(text: Any) -> str:
        """Normalize extracted fact text while preserving meaning."""
        if not isinstance(text, str):
            return ""

        normalized = " ".join(text.strip().split())
        return normalized.rstrip(" .,!?:;\t\r\n")

    @staticmethod
    def _normalize_name(name: Any) -> str:
        """Normalize display names for owner-local subject refs."""
        if not isinstance(name, str):
            return ""
        normalized = unicodedata.normalize("NFKC", name)
        return " ".join(normalized.casefold().split())

    @staticmethod
    def _normalize_relation_type(value: Any) -> str:
        relation = Memory._normalize_fact_text(value or "person").casefold()
        relation = relation.replace(" ", "_")
        relation_map = {
            "mom": "mother",
            "dad": "father",
            "wife": "partner",
            "husband": "partner",
            "girlfriend": "partner",
            "boyfriend": "partner",
            "colleague": "coworker",
            "brother": "sibling",
            "sister": "sibling",
            "dog": "pet",
            "cat": "pet",
        }
        return relation_map.get(relation, relation or "person")

    @staticmethod
    def _normalize_fact_family(value: Any) -> FactFamily:
        normalized = Memory._normalize_fact_text(value or FactFamily.ATTRIBUTE.value).casefold()
        try:
            return FactFamily(normalized)
        except ValueError:
            return FactFamily.ATTRIBUTE

    @staticmethod
    def _normalize_field_key(value: Any, fact_family: FactFamily) -> str:
        raw_key = Memory._normalize_fact_text(value or "")
        normalized = raw_key.casefold().replace(" ", "_").replace("-", "_")
        normalized = re.sub(r"[^a-z0-9_:]+", "", normalized)
        controlled_map = {
            "job": "occupation",
            "works_at": "workplace",
            "work": "workplace",
            "lives_in": "location",
            "city": "location",
            "profession": "occupation",
            "relation": "relation_to_owner",
        }
        normalized = controlled_map.get(normalized, normalized)
        if not normalized:
            normalized = "attribute:statement"

        if fact_family == FactFamily.RELATION:
            return "relation_to_owner"
        if fact_family == FactFamily.QUOTE:
            return "quote"
        if fact_family in _APPEND_ONLY_FAMILIES and ":" not in normalized:
            return f"{fact_family.value}:{normalized}"
        if fact_family in _SET_VALUE_FAMILIES and ":" not in normalized:
            return f"{fact_family.value}:{normalized}"
        if normalized in _SINGLE_VALUE_FIELDS or ":" in normalized:
            return normalized
        return f"attribute:{normalized}"

    @staticmethod
    def _build_canonical_text(
        subject_ref: str,
        field_key: str,
        field_value_json: Dict[str, Any],
    ) -> str:
        """Render a structured canonical memory string."""
        value = field_value_json.get("value", field_value_json)
        if field_key == "quote":
            rendered = json.dumps(str(value), ensure_ascii=False)
        elif isinstance(value, (dict, list)):
            rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
        else:
            rendered = str(value)
        return f"[{subject_ref}] {field_key}={rendered}"

    @staticmethod
    def _owner_user_id(owner: OwnerRecord) -> str:
        """Return the compatibility-facing user ID for a resolved owner."""
        return owner.external_user_id or owner.anonymous_session_id or owner.owner_id

    @staticmethod
    def _coerce_owner_context(
        user_id: Optional[str],
        owner: Optional[OwnerContext],
    ) -> OwnerContext:
        """Resolve backward-compatible ``user_id`` into ``OwnerContext``."""
        if owner is None:
            if not user_id:
                raise ValueError(
                    "Provide either user_id or owner with external_user_id / "
                    "anonymous_session_id"
                )
            return OwnerContext(external_user_id=user_id)

        owner_data = owner.model_dump()
        if user_id:
            existing_external = owner_data.get("external_user_id")
            if existing_external and existing_external != user_id:
                raise ValueError("user_id conflicts with owner.external_user_id")
            owner_data["external_user_id"] = user_id
        return OwnerContext(**owner_data)

    def _stl_extraction_temperature(self) -> Optional[float]:
        """Resolve STL extraction temperature from stage config with fallback."""
        stl_cfg = self._config.llm_stages.get("stl_extraction")
        if stl_cfg and stl_cfg.extraction_temperature is not None:
            return stl_cfg.extraction_temperature
        if stl_cfg:
            return stl_cfg.temperature
        if self._config.llm.extraction_temperature is not None:
            return self._config.llm.extraction_temperature
        return self._config.llm.temperature

    # ══════════════════════════════════════════════════════════════════
    # STL pipeline helpers
    # ══════════════════════════════════════════════════════════════════

    def _extract_stl(
        self,
        conversation: str,
        owner_id: str = "",
        current_turn: int = 0,
    ) -> str:
        """Call LLM once to produce STL text from a conversation.

        When *owner_id* is provided, bootstraps the focus stack from
        stored refs and injects it into the prompt (Phase 3 §17).
        """
        # Bootstrap focus stack from history
        focus_stack = FocusStack()
        if owner_id:
            try:
                ref_rows = self._stl_store.query_recent_refs(owner_id)
                focus_stack.bootstrap_from_refs(ref_rows, current_turn)
            except Exception:
                logger.debug("Focus stack bootstrap failed", exc_info=True)
        active = focus_stack.top_k_for_prompt()
        focus_stack_text = format_focus_stack(active)
        messages = [
            {"role": "system", "content": STL_EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": STL_EXTRACTION_USER_TEMPLATE.format(
                focus_stack=focus_stack_text,
                conversation=conversation,
            )},
        ]
        return self.stl_extraction_llm.generate(
            messages=messages,
            temperature=self._stl_extraction_temperature(),
        )

    @staticmethod
    def _statement_to_canonical(stmt, program) -> str:
        """Render a statement as a human-readable canonical string for embedding."""
        ref_map = {ref.local_id: ref.expr for ref in program.refs}
        args_str = ", ".join(
            str(Memory._render_statement_arg(arg, ref_map))
            for arg in stmt.args
        )
        return f"{stmt.predicate}({args_str})"

    @staticmethod
    def _render_statement_arg(arg: Any, ref_map: Dict[str, Any]) -> Any:
        """Render a parsed STL arg into a compact JSON-safe value."""
        kind = getattr(arg, "kind", None)
        if kind == "literal":
            return arg.value
        if kind == "number":
            value = arg.value
            return int(value) if isinstance(value, float) and value.is_integer() else value
        if kind == "ref":
            if arg.ref_id in {"s", "self"}:
                return "self"
            expr = ref_map.get(arg.ref_id)
            if expr is not None and expr.key:
                return expr.key
            return arg.ref_id
        if kind == "prop":
            return f"${arg.prop_id}"
        if kind == "list":
            return [Memory._render_statement_arg(item, ref_map) for item in arg.items]
        if kind == "inline_pred":
            rendered = ", ".join(
                str(Memory._render_statement_arg(item, ref_map)) for item in arg.args
            )
            return f"{arg.predicate}({rendered})"
        return str(arg)

    def _statement_confidence(self, stmt, program) -> float:
        """Return the highest evidence confidence attached to a statement."""
        matches = [
            ev.conf
            for ev in program.evidence
            if ev.target_local_id == stmt.local_id
        ]
        return max(matches) if matches else 0.9

    def _statement_subject(self, ref_id: str, ref_map: Dict[str, Any], relation_subject_cache: Dict[str, Dict[str, str]]) -> tuple[str, str]:
        """Resolve projected subject_ref and relation_type for a local ref."""
        if ref_id in {"s", "self"}:
            return "self", "self"
        cached = relation_subject_cache.get(ref_id)
        if cached is not None:
            return cached["subject_ref"], cached["relation_type"]

        expr = ref_map.get(ref_id)
        scope = getattr(getattr(expr, "scope", None), "value", getattr(expr, "scope", None))
        if expr is not None and expr.key and scope != "blank":
            ref_type = expr.ref_type or "entity"
            normalized = self._normalize_name(expr.key) or ref_id
            return f"{ref_type}:{normalized}", ref_type
        return f"unknown:{ref_id}", "person"

    def _statement_family_and_key(self, stmt) -> tuple[FactFamily, str]:
        """Map an STL statement to a projected legacy family/key pair."""
        predicate = stmt.predicate
        mapping = {
            "name": (FactFamily.ATTRIBUTE, "name"),
            "age": (FactFamily.ATTRIBUTE, "age"),
            "occupation": (FactFamily.ATTRIBUTE, "occupation"),
            "work_at": (FactFamily.ATTRIBUTE, "workplace"),
            "live_in": (FactFamily.ATTRIBUTE, "location"),
            "like": (FactFamily.PREFERENCE, "preference:like"),
            "drink": (FactFamily.HABIT, "habit:drink"),
            "habit": (FactFamily.HABIT, "habit"),
            "hobby": (FactFamily.HABIT, "habit:hobby"),
            "buy": (FactFamily.EVENT, "event:buy"),
            "visit": (FactFamily.EVENT, "event:visit"),
            "meet": (FactFamily.EVENT, "event:meet"),
            "resign": (FactFamily.EVENT, "event:resign"),
            "plan": (FactFamily.PLAN, "plan"),
            "say": (FactFamily.QUOTE, "quote"),
            "believe": (FactFamily.BELIEF, "belief"),
        }
        if predicate in mapping:
            return mapping[predicate]
        return FactFamily.ATTRIBUTE, self._normalize_field_key(predicate, FactFamily.ATTRIBUTE)

    def _statement_value_json(self, stmt, ref_map: Dict[str, Any]) -> Dict[str, Any]:
        """Project the non-subject portion of a statement into field_value_json."""
        if len(stmt.args) <= 1:
            return {"value": stmt.predicate}

        rendered = [
            self._render_statement_arg(arg, ref_map)
            for arg in stmt.args[1:]
        ]
        if len(rendered) == 1:
            return {"value": rendered[0]}
        return {"value": rendered}

    def _statement_to_envelope(
        self,
        stmt,
        program,
        owner_record: OwnerRecord,
        session_id: Optional[str],
        source_context: str,
        metadata: Optional[Dict[str, Any]],
        relation_subject_cache: Dict[str, Dict[str, str]],
    ) -> Optional[FactEnvelope]:
        """Project one STL statement into a legacy owner-centered memory envelope."""
        ref_map = {ref.local_id: ref.expr for ref in program.refs}
        confidence = self._statement_confidence(stmt, program)

        if (
            stmt.predicate in _OWNER_RELATION_PREDICATES
            and len(stmt.args) >= 2
            and getattr(stmt.args[0], "kind", None) == "ref"
            and stmt.args[0].ref_id in {"s", "self"}
            and getattr(stmt.args[1], "kind", None) == "ref"
        ):
            subject_ref, relation_type = self._statement_subject(
                stmt.args[1].ref_id,
                ref_map,
                relation_subject_cache,
            )
            field_value_json = {"value": relation_type}
            canonical_text = self._build_canonical_text(
                subject_ref=subject_ref,
                field_key="relation_to_owner",
                field_value_json=field_value_json,
            )
            return FactEnvelope(
                owner_id=owner_record.owner_id,
                user_id=self._owner_user_id(owner_record),
                owner_type=owner_record.owner_type,
                subject_ref=subject_ref,
                fact_family=FactFamily.RELATION,
                relation_type=relation_type,
                field_key="relation_to_owner",
                field_value_json=field_value_json,
                canonical_text=canonical_text,
                raw_text=f"${stmt.local_id} = {self._statement_to_canonical(stmt, program)}",
                confidence=confidence,
                source_context=source_context,
                source_session_id=session_id,
                metadata=metadata or {},
            )

        if stmt.args and getattr(stmt.args[0], "kind", None) == "ref":
            subject_ref, relation_type = self._statement_subject(
                stmt.args[0].ref_id,
                ref_map,
                relation_subject_cache,
            )
        else:
            subject_ref, relation_type = "self", "self"

        fact_family, field_key = self._statement_family_and_key(stmt)
        field_value_json = self._statement_value_json(stmt, ref_map)
        canonical_text = self._build_canonical_text(
            subject_ref=subject_ref,
            field_key=field_key,
            field_value_json=field_value_json,
        )

        return FactEnvelope(
            owner_id=owner_record.owner_id,
            user_id=self._owner_user_id(owner_record),
            owner_type=owner_record.owner_type,
            subject_ref=subject_ref,
            fact_family=fact_family,
            relation_type=relation_type,
            field_key=field_key,
            field_value_json=field_value_json,
            canonical_text=canonical_text,
            raw_text=f"${stmt.local_id} = {self._statement_to_canonical(stmt, program)}",
            confidence=confidence,
            source_context=source_context,
            source_session_id=session_id,
            metadata=metadata or {},
        )

    def _store_stl_memory(
        self,
        stmt,
        canonical: str,
        vector: list,
        owner_record: OwnerRecord,
        batch_id: str,
        session_id: Optional[str],
        metadata: Optional[Dict[str, Any]],
    ) -> MemoryItem:
        """Persist a single STL statement as a vector-store memory."""
        now = get_utc_now()
        memory_id = f"{batch_id}_{stmt.local_id}"
        user_id = self._owner_user_id(owner_record)
        payload = {
            "user_id": user_id,
            "owner_id": owner_record.owner_id,
            "content": canonical,
            "canonical_text": canonical,
            "raw_text": f"${stmt.local_id} = {canonical}",
            "hash": generate_hash(canonical),
            "metadata": metadata or {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "confidence": 1.0,
            "status": MemoryStatus.ACTIVE.value,
            "source_session_id": session_id,
            "stl_batch_id": batch_id,
            "stl_predicate": stmt.predicate,
            "stl_category": stmt.category,
        }
        self._vector_store.insert(id=memory_id, vector=vector, payload=payload)
        self._history_store.add_record(
            memory_id=memory_id,
            user_id=user_id,
            operation=MemoryOperation.ADD,
            new_content=canonical,
        )
        return self._payload_to_item(memory_id, payload)

    def _retrieve_similar(
        self,
        fact_text: Optional[str] = None,
        user_id: Optional[str] = None,
        envelope: Optional[FactEnvelope] = None,
    ) -> tuple:
        """Embed a fact and find similar existing memories."""
        if envelope is not None:
            fact_text = envelope.canonical_text
        if not fact_text:
            raise ValueError("fact_text or envelope is required")
        fact_vector = self.embedder.embed(fact_text)
        filters = {"status": MemoryStatus.ACTIVE.value}
        if envelope is not None:
            filters.update(
                {
                    "owner_id": envelope.owner_id,
                    "subject_ref": envelope.subject_ref,
                    "fact_family": envelope.fact_family.value,
                    "field_key": envelope.field_key,
                }
            )
        elif user_id:
            filters["user_id"] = user_id

        similar = self._vector_store.search(
            query_vector=fact_vector,
            limit=self._config.retrieval.similarity_top_k,
            filters=filters,
        )

        temp_to_real: Dict[str, str] = {}
        for idx, s in enumerate(similar):
            temp_to_real[str(idx)] = s["id"]

        return fact_vector, similar, temp_to_real

    @staticmethod
    def _decide_action(
        fact_text: str,
        similar_results: list,
        llm,
    ) -> Optional[Dict[str, Any]]:
        """Decide ADD / UPDATE / DELETE / NONE for a single fact.

        Args:
            fact_text: The extracted fact string.
            similar_results: Raw search results from retrieval.
            llm: The LLM client to use.

        Returns:
            Parsed decision dict with keys ``action``, ``id``, ``text``,
            ``reason``, or *None* if JSON parsing fails.
        """
        memory_list = [
            {"content": s.get("payload", {}).get("content", "")}
            for s in similar_results
        ]
        existing_text = format_existing_memories(memory_list)

        decision_messages = [
            {"role": "system", "content": UPDATE_DECISION_SYSTEM_PROMPT},
            {"role": "user", "content": UPDATE_DECISION_USER_TEMPLATE.format(
                existing_memories=existing_text, new_fact=fact_text)},
        ]
        decision_response = llm.generate(
            messages=decision_messages,
            response_format={"type": "json_object"},
        )

        try:
            decision = json.loads(decision_response)
        except json.JSONDecodeError:
            logger.error("Failed to parse update decision: %s", decision_response)
            return None

        action = decision.get("action", "NONE").upper()
        reason = decision.get("reason", "")
        logger.info("Fact: '%s' → Decision: %s (reason: %s)", fact_text[:60], action, reason)
        return decision

    @staticmethod
    def _update_mode(envelope: FactEnvelope) -> str:
        """Return the update strategy for a structured envelope."""
        if envelope.fact_family in _APPEND_ONLY_FAMILIES:
            return "append_only"
        if envelope.field_key in _SINGLE_VALUE_FIELDS:
            return "single_value"
        if envelope.fact_family in _SET_VALUE_FAMILIES:
            return "set_value"
        return "llm"

    @staticmethod
    def _has_exact_canonical_match(
        envelope: FactEnvelope,
        similar_results: List[Dict[str, Any]],
    ) -> bool:
        """Check whether retrieval found an exact canonical duplicate."""
        target = envelope.canonical_text.casefold()
        return any(
            (
                s.get("payload", {}).get("canonical_text")
                or s.get("payload", {}).get("content", "")
            ).casefold() == target
            for s in similar_results
        )

    def _execute_action(
        self,
        decision: Dict[str, Any],
        envelope: FactEnvelope,
        fact_vector: list,
        temp_to_real: Dict[str, str],
    ) -> Optional[MemoryItem]:
        """Execute ADD / UPDATE / DELETE / NONE based on the decision output."""
        action = decision.get("action", "NONE").upper()

        if action == "ADD":
            return self._execute_add(
                envelope=self._apply_decision_text(envelope, decision),
                vector=fact_vector,
            )

        elif action == "UPDATE":
            temp_id = str(decision.get("id", ""))
            real_id = temp_to_real.get(temp_id)
            if real_id is None:
                logger.warning(
                    "UPDATE referenced invalid ID: %s — falling back to ADD",
                    temp_id,
                )
                return self._execute_add(
                    envelope=self._apply_decision_text(envelope, decision),
                    vector=fact_vector,
                )
            return self._execute_update(
                old_memory_id=real_id,
                envelope=self._apply_decision_text(envelope, decision),
            )

        elif action == "DELETE":
            temp_id = str(decision.get("id", ""))
            real_id = temp_to_real.get(temp_id)
            if real_id:
                self.delete(real_id)
            return None

        else:  # NONE
            logger.debug("No action for fact: %s", envelope.canonical_text[:60])
            return None

    # ══════════════════════════════════════════════════════════════════
    # Internal orchestration & storage helpers
    # ══════════════════════════════════════════════════════════════════

    def _process_envelope(
        self,
        envelope: FactEnvelope,
    ) -> Optional[MemoryItem]:
        """Process a normalized envelope through retrieval → decision → execution."""
        fact_vector, similar, temp_to_real = self._retrieve_similar(
            envelope=envelope,
        )
        if self._has_exact_canonical_match(envelope, similar):
            return None

        mode = self._update_mode(envelope)
        if mode == "append_only":
            return self._execute_add(envelope=envelope, vector=fact_vector)
        if mode == "single_value":
            if not similar:
                return self._execute_add(envelope=envelope, vector=fact_vector)
            return self._execute_update(
                old_memory_id=similar[0]["id"],
                envelope=envelope,
            )

        decision = self._decide_action(
            fact_text=envelope.canonical_text,
            similar_results=similar,
            llm=self.decision_llm,
        )
        if decision is None:
            return None

        return self._execute_action(
            decision=decision,
            envelope=envelope,
            fact_vector=fact_vector,
            temp_to_real=temp_to_real,
        )

    def _execute_add(
        self,
        envelope: FactEnvelope,
        vector: List[float],
    ) -> MemoryItem:
        """Persist a new memory to vector store and history."""
        now = get_utc_now()
        memory_id = generate_id()
        payload = {
            "user_id": envelope.user_id,
            "owner_id": envelope.owner_id,
            "subject_ref": envelope.subject_ref,
            "fact_family": envelope.fact_family.value,
            "relation_type": envelope.relation_type,
            "field_key": envelope.field_key,
            "field_value_json": envelope.field_value_json,
            "canonical_text": envelope.canonical_text,
            "raw_text": envelope.raw_text,
            "content": envelope.canonical_text,
            "hash": generate_hash(envelope.canonical_text),
            "metadata": envelope.metadata,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "confidence": envelope.confidence,
            "status": MemoryStatus.ACTIVE.value,
            "source_context": envelope.source_context,
            "source_session_id": envelope.source_session_id,
            "version_of": None,
        }
        self._vector_store.insert(id=memory_id, vector=vector, payload=payload)
        self._history_store.add_record(
            memory_id=memory_id,
            user_id=envelope.user_id,
            operation=MemoryOperation.ADD,
            new_content=envelope.canonical_text,
            metadata=self._history_snapshot(envelope),
        )
        logger.info("Added memory %s: %s", memory_id, envelope.canonical_text[:60])
        return self._payload_to_item(memory_id, payload)

    def _execute_update(
        self,
        old_memory_id: str,
        envelope: FactEnvelope,
    ) -> MemoryItem:
        """Create a new version of an existing memory (re-embeds)."""
        old_memory = self.get(old_memory_id)
        old_content = old_memory.content if old_memory else None

        new_vector = self.embedder.embed(envelope.canonical_text)
        now = get_utc_now()
        new_memory_id = generate_id()
        payload = {
            "user_id": envelope.user_id,
            "owner_id": envelope.owner_id,
            "subject_ref": envelope.subject_ref,
            "fact_family": envelope.fact_family.value,
            "relation_type": envelope.relation_type,
            "field_key": envelope.field_key,
            "field_value_json": envelope.field_value_json,
            "canonical_text": envelope.canonical_text,
            "raw_text": envelope.raw_text,
            "content": envelope.canonical_text,
            "hash": generate_hash(envelope.canonical_text),
            "metadata": envelope.metadata,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "confidence": envelope.confidence,
            "status": MemoryStatus.ACTIVE.value,
            "source_context": envelope.source_context,
            "source_session_id": envelope.source_session_id,
            "version_of": old_memory_id,
        }
        self._vector_store.insert(id=new_memory_id, vector=new_vector, payload=payload)
        self._vector_store.update(
            id=old_memory_id,
            payload={
                "status": MemoryStatus.DELETED.value,
                "updated_at": now.isoformat(),
            },
        )
        self._history_store.add_record(
            memory_id=new_memory_id,
            user_id=envelope.user_id,
            operation=MemoryOperation.ADD,
            new_content=envelope.canonical_text,
            metadata=self._history_snapshot(
                envelope,
                extra={"version_of": old_memory_id},
            ),
        )
        self._history_store.add_record(
            memory_id=old_memory_id,
            user_id=envelope.user_id,
            operation=MemoryOperation.UPDATE,
            old_content=old_content,
            new_content=envelope.canonical_text,
            metadata=self._history_snapshot(
                envelope,
                extra={"superseded_by": new_memory_id},
            ),
        )
        logger.info("Updated: %s → %s (version_of=%s)", old_memory_id, new_memory_id, old_memory_id)
        return self._payload_to_item(new_memory_id, payload)

    @staticmethod
    def _history_snapshot(
        envelope: FactEnvelope,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build rich history metadata for owner-centered writes."""
        snapshot = {
            "owner_id": envelope.owner_id,
            "subject_ref": envelope.subject_ref,
            "fact_family": envelope.fact_family.value,
            "relation_type": envelope.relation_type,
            "field_key": envelope.field_key,
            "field_value_json": envelope.field_value_json,
            "canonical_text": envelope.canonical_text,
            "raw_text": envelope.raw_text,
        }
        if extra:
            snapshot.update(extra)
        return snapshot

    @staticmethod
    def _apply_decision_text(
        envelope: FactEnvelope,
        decision: Dict[str, Any],
    ) -> FactEnvelope:
        """Apply a decision-time replacement text to an envelope if needed."""
        decision_text = Memory._normalize_fact_text(decision.get("text", ""))
        if not decision_text or decision_text == envelope.canonical_text:
            return envelope
        return envelope.model_copy(
            update={
                "canonical_text": decision_text,
                "field_value_json": {"value": decision_text},
            }
        )

    @staticmethod
    def _payload_to_item(memory_id: str, payload: Dict[str, Any]) -> MemoryItem:
        """Convert a raw vector-store payload dict into a ``MemoryItem``."""
        return MemoryItem(
            id=memory_id,
            user_id=payload.get("user_id", ""),
            owner_id=payload.get("owner_id"),
            content=payload.get("content", ""),
            hash=payload.get("hash", ""),
            metadata=payload.get("metadata", {}),
            created_at=payload.get("created_at"),
            updated_at=payload.get("updated_at"),
            confidence=payload.get("confidence"),
            status=MemoryStatus(payload.get("status", "active")),
            source_context=payload.get("source_context"),
            source_session_id=payload.get("source_session_id"),
            version_of=payload.get("version_of"),
            importance=payload.get("importance"),
            type=payload.get("type"),
            subject_ref=payload.get("subject_ref"),
            fact_family=payload.get("fact_family"),
            relation_type=payload.get("relation_type"),
            field_key=payload.get("field_key"),
            field_value_json=payload.get("field_value_json") or {},
            canonical_text=payload.get("canonical_text"),
            raw_text=payload.get("raw_text"),
        )
