"""STL relational storage — Postgres and SQLite backends.

Implements the 12-table schema from §12 of the spec.  All tables are
created from day one; Phase 2/3 tables remain empty until those features
are implemented.

Follows the same dual-backend pattern as ``mind.storage`` (lazy Postgres
module loading, per-thread SQLite connections).
"""

from __future__ import annotations

import importlib
import json
import logging
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from mind.stl.models import (
    ParsedEvidence,
    ParsedNote,
    ParsedProgram,
    ParsedRef,
    ParsedStatement,
    RefScope,
    StorageResult,
)
from mind.stl.vocab import (
    CORRECTION_PREDICATES,
    QUALIFIER_PREDICATES,
    SEED_CATEGORY_MAP,
    SEED_VOCAB,
)
from mind.ops_logger import ops
from mind.utils import generate_id, get_utc_now

logger = logging.getLogger(__name__)


def _load_postgres_modules() -> Tuple[Any, Any, Any, Any]:
    """Lazy-load Postgres modules."""
    psycopg = importlib.import_module("psycopg")
    dict_row = importlib.import_module("psycopg.rows").dict_row
    sql = importlib.import_module("psycopg.sql")
    Jsonb = importlib.import_module("psycopg.types.json").Jsonb
    return psycopg, dict_row, sql, Jsonb


# ══════════════════════════════════════════════════════════════════════
# Abstract base
# ══════════════════════════════════════════════════════════════════════

class BaseSTLStore(ABC):
    """Abstract interface for STL relational storage."""

    @abstractmethod
    def create_schema(self) -> None:
        """Create all 12 tables if they don't exist."""

    @abstractmethod
    def upsert_ref(
        self,
        ref_id: str,
        scope: str,
        ref_type: Optional[str],
        key: Optional[str],
        aliases: list,
        owner_id: str,
    ) -> str:
        """Upsert an entity reference. Returns the resolved ref row ID."""

    @abstractmethod
    def get_ref_by_key(
        self, owner_id: str, scope: str, ref_type: Optional[str], key: Optional[str],
    ) -> Optional[str]:
        """Look up a ref ID by its natural key."""

    @abstractmethod
    def create_extraction_batch(
        self,
        batch_id: str,
        conv_id: str,
        turn_start: int,
        turn_end: int,
        model: Optional[str] = None,
    ) -> None:
        """Record an extraction batch."""

    @abstractmethod
    def create_conversation(self, conv_id: str) -> None:
        """Create a conversation record."""

    @abstractmethod
    def create_turn(
        self, conv_id: str, turn_index: int, role: str, content: str,
    ) -> int:
        """Insert a turn and return its serial ID."""

    @abstractmethod
    def insert_statement(
        self,
        stmt_id: str,
        batch_id: str,
        owner_id: str,
        predicate: str,
        args_json: list,
        category: Optional[str] = None,
    ) -> None:
        """Insert a statement row."""

    @abstractmethod
    def insert_stmt_ref(
        self, stmt_id: str, position: int, ref_id: str,
    ) -> None:
        """Insert a stmt_refs row."""

    @abstractmethod
    def insert_evidence(
        self,
        target_id: str,
        conf: float,
        src: Optional[str] = None,
        span: Optional[str] = None,
        residual: Optional[str] = None,
    ) -> None:
        """Insert an evidence row."""

    @abstractmethod
    def insert_note(
        self, target_id: str, content: str,
    ) -> None:
        """Insert a note row."""

    @abstractmethod
    def upsert_vocab(
        self,
        word: str,
        category: str,
        arg_schema: Optional[str],
        definition: str,
        source: str = "llm_created",
    ) -> None:
        """Upsert a vocabulary entry."""

    @abstractmethod
    def query_statements(
        self,
        owner_id: str,
        predicate: Optional[str] = None,
        ref_id: Optional[str] = None,
        is_current: bool = True,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Query statements with optional filters."""

    @abstractmethod
    def get_vocab_category(self, predicate: str) -> Optional[str]:
        """Look up a predicate's category from vocab_registry."""

    @abstractmethod
    def insert_temporal_spec(
        self,
        stmt_id: str,
        time_type: str,
        anchor_turn: int,
        resolved_start: Optional[str] = None,
        resolved_end: Optional[str] = None,
        fuzzy_desc: Optional[str] = None,
        window_days: Optional[int] = None,
    ) -> None:
        """Insert a temporal_specs row for a time() qualifier."""

    @abstractmethod
    def mark_superseded(
        self, stmt_id: str, superseded_by: str,
    ) -> None:
        """Mark a statement as superseded (is_current=FALSE)."""

    @abstractmethod
    def query_recent_refs(
        self,
        owner_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Return recent refs for bootstrapping the focus stack.

        Each dict has keys: ``id``, ``scope``, ``ref_type``, ``key``, ``aliases``.
        """

    @abstractmethod
    def insert_coreference(
        self,
        source_expr: str,
        resolved_to: str,
        turn_id: int,
        confidence: float,
        method: Optional[str] = None,
    ) -> None:
        """Record a coreference resolution event."""

    @abstractmethod
    def insert_coref_pending(
        self,
        source_expr: str,
        candidates: list,
        turn_id: int,
    ) -> None:
        """Record an ambiguous coreference for later resolution."""

    @abstractmethod
    def get_all_vocab_words(self) -> List[str]:
        """Return all words currently in vocab_registry."""

    def seed_vocab(self) -> None:
        """Pre-populate vocab_registry with seed predicates."""
        for entry in SEED_VOCAB:
            try:
                self.upsert_vocab(
                    word=entry.word,
                    category=entry.category,
                    arg_schema=entry.arg_schema,
                    definition=entry.definition,
                    source="seed",
                )
            except Exception as e:
                logger.debug("Seed vocab %r already exists or failed: %s", entry.word, e)

    def resolve_category(self, predicate: str) -> Optional[str]:
        """Resolve a predicate's category: check seed map first, then DB."""
        cat = SEED_CATEGORY_MAP.get(predicate)
        if cat:
            return cat
        return self.get_vocab_category(predicate)

    def close(self) -> None:
        """Release backend resources."""

    def check_vocab_collision(
        self,
        word: str,
        embedder=None,
        threshold: float = 0.85,
    ):
        """Check if *word* collides with existing vocab entries.

        Uses embedding similarity when *embedder* is available.
        Returns list of (existing_word, similarity) pairs above *threshold*.
        Soft alert only -- does not block registration.
        """
        if embedder is None:
            return []
        existing_words = self.get_all_vocab_words()
        if not existing_words:
            return []
        try:
            new_vec = embedder.embed(word)
        except Exception as e:
            logger.debug("Vocab collision embed failed for %r: %s", word, e)
            return []
        collisions = []
        for ew in existing_words:
            if ew == word:
                continue
            try:
                ev = embedder.embed(ew)
                sim = _cosine_sim(new_vec, ev)
                if sim >= threshold:
                    collisions.append((ew, sim))
            except Exception:
                continue
        return collisions

    # ── High-level helper ──

    def store_program(
        self,
        program: ParsedProgram,
        owner_id: str,
        conv_id: str,
        model: Optional[str] = None,
        embedder=None,
    ) -> StorageResult:
        """Persist an entire ParsedProgram.

        Handles ID globalization: $local_id → {batch_id}_{local_id},
        @id resolved by (owner_id, scope, ref_type, key) upsert.
        """
        result = StorageResult(batch_id=program.batch_id)
        batch_id = program.batch_id
        # Maps: local @id → resolved global ref ID
        ref_map: Dict[str, str] = {}
        # Maps: local $id → globalized statement ID
        stmt_map: Dict[str, str] = {}

        # 1. Create extraction batch
        turn_count = 0  # will be overridden by caller if known
        try:
            self.create_extraction_batch(
                batch_id=batch_id,
                conv_id=conv_id,
                turn_start=0,
                turn_end=turn_count,
                model=model,
            )
        except Exception as e:
            logger.warning("Failed to create extraction_batch: %s", e)
            result.errors.append(f"extraction_batch: {e}")

        # 2. Upsert refs
        # Always ensure @self exists for this owner
        self_ref_id = self._resolve_self_ref(owner_id)
        ref_map["self"] = self_ref_id
        ref_map["s"] = self_ref_id  # common alias

        for ref in program.refs:
            try:
                if ref.expr.scope == RefScope.SELF:
                    ref_map[ref.local_id] = self_ref_id
                    continue

                resolved_id = self.upsert_ref(
                    ref_id=f"{batch_id}_{ref.local_id}",
                    scope=ref.expr.scope.value,
                    ref_type=ref.expr.ref_type,
                    key=ref.expr.key,
                    aliases=ref.expr.aliases,
                    owner_id=owner_id,
                )
                ref_map[ref.local_id] = resolved_id
                result.refs_upserted += 1
            except Exception as e:
                logger.warning("Failed to upsert ref @%s: %s", ref.local_id, e)
                result.errors.append(f"ref @{ref.local_id}: {e}")

        # 3. Insert statements (with category resolution)
        correction_stmts: List[Tuple[str, ParsedStatement, list]] = []
        for stmt in program.statements:
            global_id = f"{batch_id}_{stmt.local_id}"
            stmt_map[stmt.local_id] = global_id
            # Globalize args JSON
            args_json = _globalize_args(stmt.args, ref_map, stmt_map)
            # Resolve category from vocab (seed map → DB → None)
            category = stmt.category or self.resolve_category(stmt.predicate)
            try:
                self.insert_statement(
                    stmt_id=global_id,
                    batch_id=batch_id,
                    owner_id=owner_id,
                    predicate=stmt.predicate,
                    args_json=args_json,
                    category=category,
                )
                result.statements_inserted += 1

                # Insert stmt_refs for indexing
                for pos, arg_json in enumerate(args_json):
                    if isinstance(arg_json, str) and (
                        arg_json.startswith("@") or arg_json.startswith("$")
                    ):
                        self.insert_stmt_ref(global_id, pos, arg_json)

                # Detect time() qualifiers → populate temporal_specs
                if stmt.predicate in QUALIFIER_PREDICATES and stmt.predicate == "time":
                    self._handle_time_qualifier(global_id, args_json)

                # Collect correct_intent / retract_intent for post-processing
                if stmt.predicate in CORRECTION_PREDICATES:
                    correction_stmts.append((global_id, stmt, args_json))

            except Exception as e:
                logger.warning("Failed to insert statement $%s: %s", stmt.local_id, e)
                result.errors.append(f"stmt ${stmt.local_id}: {e}")

        # 4. Insert evidence
        for ev in program.evidence:
            target_global = stmt_map.get(ev.target_local_id, f"{batch_id}_{ev.target_local_id}")
            try:
                self.insert_evidence(
                    target_id=target_global,
                    conf=ev.conf,
                    src=ev.src,
                    span=ev.span,
                    residual=ev.residual,
                )
                result.evidence_inserted += 1
            except Exception as e:
                logger.warning("Failed to insert evidence for $%s: %s", ev.target_local_id, e)
                result.errors.append(f"ev ${ev.target_local_id}: {e}")

        # 5. Insert notes + detect NEW_PRED
        # Collect CORRECTION: notes for matching old statements
        correction_note_map: Dict[str, str] = {}  # correction_stmt_global_id → note text
        for note in program.notes:
            target_global = stmt_map.get(note.target_local_id, f"{batch_id}_{note.target_local_id}")
            try:
                self.insert_note(target_global, note.text)
                result.notes_inserted += 1
                # Detect NEW_PRED declarations
                if note.text.startswith("NEW_PRED "):
                    self._handle_new_pred(note.text, embedder=embedder)
                    result.vocab_registered += 1
                # Collect CORRECTION notes for correction workflow
                if "CORRECTION:" in note.text:
                    correction_note_map[target_global] = note.text
            except Exception as e:
                logger.warning("Failed to insert note: %s", e)
                result.errors.append(f"note: {e}")

        # 6. Process correct_intent / retract_intent
        for global_id, stmt, args_json in correction_stmts:
            try:
                self._handle_correction(
                    correction_stmt_id=global_id,
                    predicate=stmt.predicate,
                    args_json=args_json,
                    owner_id=owner_id,
                    note_text=correction_note_map.get(global_id),
                )
            except Exception as e:
                logger.warning("Correction handling failed for $%s: %s", stmt.local_id, e)
                result.errors.append(f"correction ${stmt.local_id}: {e}")

        return result

    def _resolve_self_ref(self, owner_id: str) -> str:
        """Ensure @self ref exists for this owner, return its ID."""
        existing = self.get_ref_by_key(owner_id, "self", None, None)
        if existing:
            return existing
        ref_id = f"self_{owner_id[:8]}"
        self.upsert_ref(
            ref_id=ref_id,
            scope="self",
            ref_type=None,
            key=None,
            aliases=[],
            owner_id=owner_id,
        )
        return ref_id

    def _handle_new_pred(self, note_text: str, embedder=None) -> None:
        """Parse a NEW_PRED note and register the vocabulary entry.

        Format: NEW_PRED word | category | arg_schema | definition
        When *embedder* is provided, checks for vocab collision first.
        """
        parts = note_text[len("NEW_PRED "):].split("|")
        if len(parts) < 4:
            logger.warning("Malformed NEW_PRED: %s", note_text)
            return
        word = parts[0].strip()
        category = parts[1].strip()
        arg_schema = parts[2].strip() or None
        definition = parts[3].strip()
        # Collision detection (soft alert)
        collisions = self.check_vocab_collision(word, embedder=embedder)
        if collisions:
            for cw, sim in collisions:
                logger.warning(
                    "Vocab collision: new pred %r similar to existing %r (sim=%.3f)",
                    word, cw, sim,
                )
        try:
            self.upsert_vocab(word, category, arg_schema, definition, "llm_created")
        except Exception as e:
            logger.warning("Failed to register vocab %r: %s", word, e)

    def _handle_time_qualifier(
        self, stmt_id: str, args_json: list, anchor_turn: int = 0,
        anchor_date: Optional[_date] = None,
    ) -> None:
        """Extract temporal info from a time() qualifier and write to temporal_specs."""
        # time($target, "value") or time($target, "start", "end")
        if len(args_json) < 2:
            return
        raw_value = args_json[1] if len(args_json) >= 2 else None
        raw_end = args_json[2] if len(args_json) >= 3 else None

        if not isinstance(raw_value, str):
            return

        time_type, resolved_start, resolved_end, fuzzy_desc, window_days = (
            _classify_time_value(raw_value, raw_end, anchor_date=anchor_date)
        )
        try:
            self.insert_temporal_spec(
                stmt_id=stmt_id,
                time_type=time_type,
                anchor_turn=anchor_turn,
                resolved_start=resolved_start,
                resolved_end=resolved_end,
                fuzzy_desc=fuzzy_desc,
                window_days=window_days,
            )
        except Exception as e:
            logger.warning("Failed to insert temporal_spec for %s: %s", stmt_id, e)

    def _handle_correction(
        self,
        correction_stmt_id: str,
        predicate: str,
        args_json: list,
        owner_id: str,
        note_text: Optional[str] = None,
    ) -> None:
        """Process a correct_intent or retract_intent statement.

        Finds matching existing statements by predicate/ref overlap and marks
        them as superseded.  Uses heuristic matching (Phase 2); embedding
        similarity matching deferred to Phase 3.
        """
        # The correction wraps a new statement: correct_intent(@speaker, $new_stmt)
        # Extract the target proposition ID from args
        target_prop_id = None
        for arg in args_json:
            if isinstance(arg, str) and arg.startswith("$"):
                target_prop_id = arg.lstrip("$")
                break

        if not target_prop_id:
            logger.debug("Correction %s has no target prop — skipping", correction_stmt_id)
            return

        # Look up the new statement to get its predicate and refs
        candidates = self.query_statements(owner_id, is_current=True)
        new_stmt = None
        for c in candidates:
            if c["id"] == target_prop_id:
                new_stmt = c
                break

        if not new_stmt:
            logger.debug("Correction target %s not found in DB", target_prop_id)
            return

        # Find existing statements with same predicate that are candidates for superseding
        existing = self.query_statements(
            owner_id, predicate=new_stmt["predicate"], is_current=True,
        )

        for old in existing:
            if old["id"] == target_prop_id:
                continue  # don't supersede itself
            # Heuristic: same predicate + overlapping refs = likely match
            old_args = old.get("args", [])
            new_args = new_stmt.get("args", [])
            old_refs = {a for a in old_args if isinstance(a, str) and a.startswith("@")}
            new_refs = {a for a in new_args if isinstance(a, str) and a.startswith("@")}
            overlap = old_refs & new_refs
            if overlap:
                if predicate == "retract_intent":
                    self.mark_superseded(old["id"], correction_stmt_id)
                else:
                    self.mark_superseded(old["id"], target_prop_id)
                logger.info(
                    "Superseded statement %s by %s (correction: %s)",
                    old["id"], target_prop_id, predicate,
                )


# ── Cosine similarity helper ─────────────────────────────────────────

import math as _math


def _cosine_sim(a: list, b: list) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na = _math.sqrt(sum(x * x for x in a))
    nb = _math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ── Time classification helper ───────────────────────────────────────

import re as _re
from datetime import date as _date, timedelta as _timedelta

_RE_ABSOLUTE_DATE = _re.compile(
    r"^\d{4}(?:-\d{1,2})?(?:-\d{1,2})?$"
)
_FUZZY_WORDS = {
    "recent", "recently", "past", "long_ago", "soon", "near_future",
    "recent_start", "childhood", "youth",
}

# Relative time expressions that can be resolved to absolute dates
_RELATIVE_RESOLVERS: Dict[str, Any] = {}  # populated below


def _resolve_relative_time(
    expr: str, anchor: _date,
) -> Tuple[Optional[str], Optional[str]]:
    """Resolve a relative time expression to (resolved_start, resolved_end).

    Returns (None, None) if the expression cannot be resolved.
    """
    val = expr.lower().replace(" ", "_")

    # Year-relative
    if val in ("last_year", "去年"):
        return (str(anchor.year - 1), None)
    if val in ("this_year", "今年"):
        return (str(anchor.year), None)
    if val in ("next_year", "明年"):
        return (str(anchor.year + 1), None)

    # Month-relative
    if val in ("last_month", "上个月", "上月"):
        first = anchor.replace(day=1)
        prev = first - _timedelta(days=1)
        return (f"{prev.year}-{prev.month:02d}", None)
    if val in ("this_month", "这个月", "本月"):
        return (f"{anchor.year}-{anchor.month:02d}", None)
    if val in ("next_month", "下个月", "下月"):
        if anchor.month == 12:
            return (f"{anchor.year + 1}-01", None)
        return (f"{anchor.year}-{anchor.month + 1:02d}", None)

    # Week-relative
    if val in ("this_weekend", "这周末", "周末"):
        # Saturday of the current week
        days_to_sat = (5 - anchor.weekday()) % 7
        if days_to_sat == 0 and anchor.weekday() != 5:
            days_to_sat = 7
        sat = anchor + _timedelta(days=days_to_sat)
        sun = sat + _timedelta(days=1)
        return (sat.isoformat(), sun.isoformat())
    if val in ("next_week", "下周", "下星期"):
        # Monday of next week
        days_to_mon = (7 - anchor.weekday()) % 7 or 7
        mon = anchor + _timedelta(days=days_to_mon)
        return (mon.isoformat(), None)
    if val in ("last_week", "上周", "上星期"):
        mon = anchor - _timedelta(days=anchor.weekday() + 7)
        return (mon.isoformat(), None)

    # Day-relative
    if val in ("today", "今天"):
        return (anchor.isoformat(), None)
    if val in ("yesterday", "昨天"):
        return ((anchor - _timedelta(days=1)).isoformat(), None)
    if val in ("tomorrow", "明天"):
        return ((anchor + _timedelta(days=1)).isoformat(), None)
    if val in ("day_before_yesterday", "前天"):
        return ((anchor - _timedelta(days=2)).isoformat(), None)
    if val in ("day_after_tomorrow", "后天"):
        return ((anchor + _timedelta(days=2)).isoformat(), None)

    return (None, None)


def _classify_time_value(
    raw_value: str,
    raw_end: Optional[str] = None,
    anchor_date: Optional[_date] = None,
) -> Tuple[str, Optional[str], Optional[str], Optional[str], Optional[int]]:
    """Classify a time value into (time_type, resolved_start, resolved_end, fuzzy_desc, window_days).

    When *anchor_date* is provided, relative expressions like "next_month"
    are resolved to absolute dates (§18).
    """
    if raw_end is not None:
        # Interval: time($p, "2026-04", "2026-06")
        return ("interval", raw_value, raw_end, None, None)

    if _RE_ABSOLUTE_DATE.match(raw_value):
        # Point: time($p, "2026-04")
        return ("point", raw_value, None, None, None)

    # Try to resolve relative expressions to absolute dates
    val_lower = raw_value.lower()
    if anchor_date is not None:
        resolved_start, resolved_end = _resolve_relative_time(raw_value, anchor_date)
        if resolved_start is not None:
            if resolved_end is not None:
                return ("interval", resolved_start, resolved_end, raw_value, None)
            return ("point", resolved_start, None, raw_value, None)

    # Check for known fuzzy words
    if val_lower in _FUZZY_WORDS or not _RE_ABSOLUTE_DATE.match(raw_value):
        window = 30 if val_lower in ("recent", "recently", "recent_start") else None
        return ("fuzzy", None, None, raw_value, window)

    return ("point", raw_value, None, None, None)


def _globalize_args(
    args: list,
    ref_map: Dict[str, str],
    stmt_map: Dict[str, str],
) -> list:
    """Convert parsed args into a JSON-serializable list with global IDs."""
    result = []
    for arg in args:
        kind = getattr(arg, "kind", None)
        if kind == "ref":
            global_ref = ref_map.get(arg.ref_id, f"@{arg.ref_id}")
            result.append(f"@{global_ref}" if not global_ref.startswith("@") else global_ref)
        elif kind == "prop":
            global_stmt = stmt_map.get(arg.prop_id, f"${arg.prop_id}")
            result.append(f"${global_stmt}" if not global_stmt.startswith("$") else global_stmt)
        elif kind == "literal":
            result.append(arg.value)
        elif kind == "number":
            result.append(arg.value)
        elif kind == "list":
            result.append([_globalize_single_arg(item, ref_map, stmt_map) for item in arg.items])
        else:
            result.append(str(arg))
    return result


def _globalize_single_arg(arg: Any, ref_map: dict, stmt_map: dict) -> Any:
    """Globalize a single arg (for list items)."""
    kind = getattr(arg, "kind", None)
    if kind == "ref":
        g = ref_map.get(arg.ref_id, f"@{arg.ref_id}")
        return f"@{g}" if not g.startswith("@") else g
    if kind == "prop":
        g = stmt_map.get(arg.prop_id, f"${arg.prop_id}")
        return f"${g}" if not g.startswith("$") else g
    if kind == "literal":
        return arg.value
    if kind == "number":
        return arg.value
    return str(arg)


# ══════════════════════════════════════════════════════════════════════
# DDL (shared across backends — parameterized for dialect)
# ══════════════════════════════════════════════════════════════════════

_POSTGRES_SCHEMA_DDL = """\
-- ========== 会话与轮次 ==========
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    started_at  TIMESTAMPTZ DEFAULT NOW(),
    metadata    JSONB DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS turns (
    id          SERIAL PRIMARY KEY,
    conv_id     TEXT NOT NULL REFERENCES conversations(id),
    turn_index  INT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (conv_id, turn_index)
);

CREATE TABLE IF NOT EXISTS extraction_batches (
    id          TEXT PRIMARY KEY,
    conv_id     TEXT NOT NULL REFERENCES conversations(id),
    turn_start  INT NOT NULL,
    turn_end    INT NOT NULL,
    model       TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ========== 核心语义表 ==========
CREATE TABLE IF NOT EXISTS refs (
    id          TEXT PRIMARY KEY,
    owner_id    TEXT NOT NULL,
    scope       TEXT NOT NULL,
    ref_type    TEXT,
    key         TEXT,
    aliases     JSONB DEFAULT '[]',
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (owner_id, scope, ref_type, key)
);

CREATE TABLE IF NOT EXISTS statements (
    id             TEXT PRIMARY KEY,
    batch_id       TEXT REFERENCES extraction_batches(id),
    owner_id       TEXT NOT NULL,
    predicate      TEXT NOT NULL,
    args           JSONB NOT NULL,
    category       TEXT,
    superseded_by  TEXT REFERENCES statements(id),
    is_current     BOOLEAN DEFAULT TRUE,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_statements_owner ON statements (owner_id);
CREATE INDEX IF NOT EXISTS idx_statements_predicate ON statements (predicate);
CREATE INDEX IF NOT EXISTS idx_statements_current ON statements (owner_id, is_current);

CREATE TABLE IF NOT EXISTS stmt_refs (
    stmt_id     TEXT NOT NULL,
    position    INT NOT NULL,
    ref_id      TEXT NOT NULL,
    PRIMARY KEY (stmt_id, position)
);
CREATE INDEX IF NOT EXISTS idx_stmt_refs_ref ON stmt_refs (ref_id);

CREATE TABLE IF NOT EXISTS evidence (
    id          SERIAL PRIMARY KEY,
    target_id   TEXT NOT NULL,
    conf        REAL NOT NULL,
    src         TEXT,
    span        TEXT,
    residual    TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_evidence_target ON evidence (target_id);

CREATE TABLE IF NOT EXISTS notes (
    id          SERIAL PRIMARY KEY,
    target_id   TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS vocab_registry (
    word         TEXT PRIMARY KEY,
    category     TEXT NOT NULL CHECK (category IN ('prop','frame','qualifier','ref_type')),
    arg_schema   TEXT,
    definition   TEXT NOT NULL,
    source       TEXT DEFAULT 'seed',
    usage_count  INT DEFAULT 0,
    status       TEXT DEFAULT 'candidate'
                 CHECK (status IN ('candidate','established','seed','dormant','archived')),
    first_seen_turn INT,
    last_used_turn  INT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    last_used    TIMESTAMPTZ
);

-- ========== Phase 2/3 tables (created empty) ==========
CREATE TABLE IF NOT EXISTS coreference (
    id          SERIAL PRIMARY KEY,
    source_expr TEXT,
    resolved_to TEXT NOT NULL,
    turn_id     INT,
    confidence  REAL NOT NULL,
    method      TEXT
);

CREATE TABLE IF NOT EXISTS coref_pending (
    id          SERIAL PRIMARY KEY,
    source_expr TEXT,
    candidates  JSONB NOT NULL,
    turn_id     INT,
    status      TEXT DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS temporal_specs (
    stmt_id        TEXT PRIMARY KEY,
    time_type      TEXT CHECK (time_type IN ('point','interval','fuzzy')),
    resolved_start TEXT,
    resolved_end   TEXT,
    fuzzy_desc     TEXT,
    window_days    INT,
    anchor_turn    INT NOT NULL
);
"""

_SQLITE_SCHEMA_DDL = """\
-- ========== 会话与轮次 ==========
CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    started_at  TEXT DEFAULT (datetime('now')),
    metadata    TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS turns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    conv_id     TEXT NOT NULL REFERENCES conversations(id),
    turn_index  INT NOT NULL,
    role        TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE (conv_id, turn_index)
);

CREATE TABLE IF NOT EXISTS extraction_batches (
    id          TEXT PRIMARY KEY,
    conv_id     TEXT NOT NULL REFERENCES conversations(id),
    turn_start  INT NOT NULL,
    turn_end    INT NOT NULL,
    model       TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);

-- ========== 核心语义表 ==========
CREATE TABLE IF NOT EXISTS refs (
    id          TEXT PRIMARY KEY,
    owner_id    TEXT NOT NULL,
    scope       TEXT NOT NULL,
    ref_type    TEXT,
    key         TEXT,
    aliases     TEXT DEFAULT '[]',
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE (owner_id, scope, ref_type, key)
);

CREATE TABLE IF NOT EXISTS statements (
    id             TEXT PRIMARY KEY,
    batch_id       TEXT REFERENCES extraction_batches(id),
    owner_id       TEXT NOT NULL,
    predicate      TEXT NOT NULL,
    args           TEXT NOT NULL,
    category       TEXT,
    superseded_by  TEXT REFERENCES statements(id),
    is_current     INTEGER DEFAULT 1,
    created_at     TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_statements_owner ON statements (owner_id);
CREATE INDEX IF NOT EXISTS idx_statements_predicate ON statements (predicate);
CREATE INDEX IF NOT EXISTS idx_statements_current ON statements (owner_id, is_current);

CREATE TABLE IF NOT EXISTS stmt_refs (
    stmt_id     TEXT NOT NULL,
    position    INT NOT NULL,
    ref_id      TEXT NOT NULL,
    PRIMARY KEY (stmt_id, position)
);
CREATE INDEX IF NOT EXISTS idx_stmt_refs_ref ON stmt_refs (ref_id);

CREATE TABLE IF NOT EXISTS evidence (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id   TEXT NOT NULL,
    conf        REAL NOT NULL,
    src         TEXT,
    span        TEXT,
    residual    TEXT,
    created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_evidence_target ON evidence (target_id);

CREATE TABLE IF NOT EXISTS notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id   TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vocab_registry (
    word         TEXT PRIMARY KEY,
    category     TEXT NOT NULL CHECK (category IN ('prop','frame','qualifier','ref_type')),
    arg_schema   TEXT,
    definition   TEXT NOT NULL,
    source       TEXT DEFAULT 'seed',
    usage_count  INT DEFAULT 0,
    status       TEXT DEFAULT 'candidate'
                 CHECK (status IN ('candidate','established','seed','dormant','archived')),
    first_seen_turn INT,
    last_used_turn  INT,
    created_at   TEXT DEFAULT (datetime('now')),
    last_used    TEXT
);

-- ========== Phase 2/3 tables (created empty) ==========
CREATE TABLE IF NOT EXISTS coreference (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_expr TEXT,
    resolved_to TEXT NOT NULL,
    turn_id     INT,
    confidence  REAL NOT NULL,
    method      TEXT
);

CREATE TABLE IF NOT EXISTS coref_pending (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_expr TEXT,
    candidates  TEXT NOT NULL,
    turn_id     INT,
    status      TEXT DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS temporal_specs (
    stmt_id        TEXT PRIMARY KEY,
    time_type      TEXT CHECK (time_type IN ('point','interval','fuzzy')),
    resolved_start TEXT,
    resolved_end   TEXT,
    fuzzy_desc     TEXT,
    window_days    INT,
    anchor_turn    INT NOT NULL
);
"""


# ══════════════════════════════════════════════════════════════════════
# SQLite implementation
# ══════════════════════════════════════════════════════════════════════

class SQLiteSTLStore(BaseSTLStore):
    """SQLite-backed STL store — ideal for testing and single-user."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self.db_path = db_path
        self._local = threading.local()
        self.create_schema()
        self.seed_vocab()

    def _get_conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            self._local.conn = conn
        return conn

    def create_schema(self) -> None:
        conn = self._get_conn()
        conn.executescript(_SQLITE_SCHEMA_DDL)
        conn.commit()

    def upsert_ref(
        self,
        ref_id: str,
        scope: str,
        ref_type: Optional[str],
        key: Optional[str],
        aliases: list,
        owner_id: str,
    ) -> str:
        conn = self._get_conn()
        # Try to find existing ref by natural key
        existing_id = self.get_ref_by_key(owner_id, scope, ref_type, key)
        if existing_id:
            # Merge aliases
            row = conn.execute(
                "SELECT aliases FROM refs WHERE id = ?", (existing_id,)
            ).fetchone()
            if row:
                existing_aliases = json.loads(row["aliases"]) if row["aliases"] else []
                merged = list(set(existing_aliases + aliases))
                conn.execute(
                    "UPDATE refs SET aliases = ? WHERE id = ?",
                    (json.dumps(merged), existing_id),
                )
                conn.commit()
            return existing_id

        conn.execute(
            """INSERT INTO refs (id, owner_id, scope, ref_type, key, aliases)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ref_id, owner_id, scope, ref_type, key, json.dumps(aliases)),
        )
        conn.commit()
        return ref_id

    def get_ref_by_key(
        self, owner_id: str, scope: str, ref_type: Optional[str], key: Optional[str],
    ) -> Optional[str]:
        conn = self._get_conn()
        if ref_type is None and key is None:
            row = conn.execute(
                "SELECT id FROM refs WHERE owner_id = ? AND scope = ? AND ref_type IS NULL AND key IS NULL",
                (owner_id, scope),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT id FROM refs WHERE owner_id = ? AND scope = ? AND ref_type = ? AND key = ?",
                (owner_id, scope, ref_type, key),
            ).fetchone()
        return row["id"] if row else None

    def create_conversation(self, conv_id: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO conversations (id) VALUES (?)", (conv_id,)
        )
        conn.commit()

    def create_turn(
        self, conv_id: str, turn_index: int, role: str, content: str,
    ) -> int:
        conn = self._get_conn()
        cur = conn.execute(
            """INSERT INTO turns (conv_id, turn_index, role, content)
               VALUES (?, ?, ?, ?)""",
            (conv_id, turn_index, role, content),
        )
        conn.commit()
        return cur.lastrowid

    def create_extraction_batch(
        self,
        batch_id: str,
        conv_id: str,
        turn_start: int,
        turn_end: int,
        model: Optional[str] = None,
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR IGNORE INTO extraction_batches (id, conv_id, turn_start, turn_end, model)
               VALUES (?, ?, ?, ?, ?)""",
            (batch_id, conv_id, turn_start, turn_end, model),
        )
        conn.commit()

    def insert_statement(
        self,
        stmt_id: str,
        batch_id: str,
        owner_id: str,
        predicate: str,
        args_json: list,
        category: Optional[str] = None,
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO statements (id, batch_id, owner_id, predicate, args, category)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (stmt_id, batch_id, owner_id, predicate, json.dumps(args_json), category),
        )
        conn.commit()

    def insert_stmt_ref(self, stmt_id: str, position: int, ref_id: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO stmt_refs (stmt_id, position, ref_id) VALUES (?, ?, ?)",
            (stmt_id, position, ref_id),
        )
        conn.commit()

    def insert_evidence(
        self,
        target_id: str,
        conf: float,
        src: Optional[str] = None,
        span: Optional[str] = None,
        residual: Optional[str] = None,
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO evidence (target_id, conf, src, span, residual)
               VALUES (?, ?, ?, ?, ?)""",
            (target_id, conf, src, span, residual),
        )
        conn.commit()

    def insert_note(self, target_id: str, content: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO notes (target_id, content) VALUES (?, ?)",
            (target_id, content),
        )
        conn.commit()

    def upsert_vocab(
        self,
        word: str,
        category: str,
        arg_schema: Optional[str],
        definition: str,
        source: str = "llm_created",
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO vocab_registry (word, category, arg_schema, definition, source)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT (word) DO UPDATE SET
                   usage_count = vocab_registry.usage_count + 1,
                   last_used = datetime('now')""",
            (word, category, arg_schema, definition, source),
        )
        conn.commit()

    def query_statements(
        self,
        owner_id: str,
        predicate: Optional[str] = None,
        ref_id: Optional[str] = None,
        is_current: bool = True,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        query = "SELECT * FROM statements WHERE owner_id = ?"
        params: list = [owner_id]

        if is_current:
            query += " AND is_current = 1"
        if predicate:
            query += " AND predicate = ?"
            params.append(predicate)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["args"] = json.loads(d["args"]) if isinstance(d["args"], str) else d["args"]
            results.append(d)

        # Filter by ref_id if specified (requires join with stmt_refs)
        if ref_id and results:
            stmt_ids = [r["id"] for r in results]
            placeholders = ",".join("?" * len(stmt_ids))
            matching = conn.execute(
                f"SELECT DISTINCT stmt_id FROM stmt_refs WHERE ref_id = ? AND stmt_id IN ({placeholders})",
                [ref_id] + stmt_ids,
            ).fetchall()
            matching_ids = {r["stmt_id"] for r in matching}
            results = [r for r in results if r["id"] in matching_ids]

        return results

    def get_vocab_category(self, predicate: str) -> Optional[str]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT category FROM vocab_registry WHERE word = ?", (predicate,)
        ).fetchone()
        return row["category"] if row else None

    def insert_temporal_spec(
        self,
        stmt_id: str,
        time_type: str,
        anchor_turn: int,
        resolved_start: Optional[str] = None,
        resolved_end: Optional[str] = None,
        fuzzy_desc: Optional[str] = None,
        window_days: Optional[int] = None,
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT OR REPLACE INTO temporal_specs
               (stmt_id, time_type, resolved_start, resolved_end, fuzzy_desc, window_days, anchor_turn)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (stmt_id, time_type, resolved_start, resolved_end, fuzzy_desc, window_days, anchor_turn),
        )
        conn.commit()

    def mark_superseded(self, stmt_id: str, superseded_by: str) -> None:
        conn = self._get_conn()
        conn.execute(
            "UPDATE statements SET is_current = 0, superseded_by = ? WHERE id = ?",
            (superseded_by, stmt_id),
        )
        conn.commit()

    def get_all_vocab_words(self) -> List[str]:
        conn = self._get_conn()
        rows = conn.execute("SELECT word FROM vocab_registry").fetchall()
        return [row["word"] for row in rows]

    def query_recent_refs(
        self,
        owner_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            """SELECT id, scope, ref_type, key, aliases
               FROM refs WHERE owner_id = ? AND scope != 'self'
               ORDER BY created_at DESC LIMIT ?""",
            (owner_id, limit),
        ).fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["aliases"] = json.loads(d["aliases"]) if isinstance(d["aliases"], str) else d["aliases"]
            results.append(d)
        return results

    def insert_coreference(
        self,
        source_expr: str,
        resolved_to: str,
        turn_id: int,
        confidence: float,
        method: Optional[str] = None,
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO coreference (source_expr, resolved_to, turn_id, confidence, method)
               VALUES (?, ?, ?, ?, ?)""",
            (source_expr, resolved_to, turn_id, confidence, method),
        )
        conn.commit()

    def insert_coref_pending(
        self,
        source_expr: str,
        candidates: list,
        turn_id: int,
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO coref_pending (source_expr, candidates, turn_id)
               VALUES (?, ?, ?)""",
            (source_expr, json.dumps(candidates), turn_id),
        )
        conn.commit()

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn:
            conn.close()
            self._local.conn = None


# ══════════════════════════════════════════════════════════════════════
# Postgres implementation
# ══════════════════════════════════════════════════════════════════════

class PostgresSTLStore(BaseSTLStore):
    """Postgres-backed STL store — production backend."""

    def __init__(self, dsn: str) -> None:
        if not dsn:
            raise ValueError("stl_store.dsn is required for provider='postgres'")
        self.dsn = dsn
        self.create_schema()
        self.seed_vocab()

    def _connect(self):
        psycopg, dict_row, _sql, _Jsonb = _load_postgres_modules()
        return psycopg.connect(self.dsn, autocommit=True, row_factory=dict_row)

    def create_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_POSTGRES_SCHEMA_DDL)

    def upsert_ref(
        self,
        ref_id: str,
        scope: str,
        ref_type: Optional[str],
        key: Optional[str],
        aliases: list,
        owner_id: str,
    ) -> str:
        _psycopg, _dict_row, sql, Jsonb = _load_postgres_modules()
        with self._connect() as conn:
            with conn.cursor() as cur:
                # Use ON CONFLICT for atomic upsert
                cur.execute(
                    """
                    INSERT INTO refs (id, owner_id, scope, ref_type, key, aliases)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (owner_id, scope, ref_type, key) DO UPDATE SET
                        aliases = (
                            SELECT jsonb_agg(DISTINCT elem)
                            FROM (
                                SELECT jsonb_array_elements(refs.aliases) AS elem
                                UNION
                                SELECT jsonb_array_elements(%s::jsonb) AS elem
                            ) sub
                        )
                    RETURNING id
                    """,
                    (ref_id, owner_id, scope, ref_type, key,
                     Jsonb(aliases), Jsonb(aliases)),
                )
                row = cur.fetchone()
                return row["id"]

    def get_ref_by_key(
        self, owner_id: str, scope: str, ref_type: Optional[str], key: Optional[str],
    ) -> Optional[str]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                if ref_type is None and key is None:
                    cur.execute(
                        "SELECT id FROM refs WHERE owner_id = %s AND scope = %s AND ref_type IS NULL AND key IS NULL",
                        (owner_id, scope),
                    )
                else:
                    cur.execute(
                        "SELECT id FROM refs WHERE owner_id = %s AND scope = %s AND ref_type = %s AND key = %s",
                        (owner_id, scope, ref_type, key),
                    )
                row = cur.fetchone()
                return row["id"] if row else None

    def create_conversation(self, conv_id: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO conversations (id) VALUES (%s) ON CONFLICT DO NOTHING",
                    (conv_id,),
                )

    def create_turn(
        self, conv_id: str, turn_index: int, role: str, content: str,
    ) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO turns (conv_id, turn_index, role, content)
                       VALUES (%s, %s, %s, %s) RETURNING id""",
                    (conv_id, turn_index, role, content),
                )
                return cur.fetchone()["id"]

    def create_extraction_batch(
        self,
        batch_id: str,
        conv_id: str,
        turn_start: int,
        turn_end: int,
        model: Optional[str] = None,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO extraction_batches (id, conv_id, turn_start, turn_end, model)
                       VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING""",
                    (batch_id, conv_id, turn_start, turn_end, model),
                )

    def insert_statement(
        self,
        stmt_id: str,
        batch_id: str,
        owner_id: str,
        predicate: str,
        args_json: list,
        category: Optional[str] = None,
    ) -> None:
        _psycopg, _dict_row, sql, Jsonb = _load_postgres_modules()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO statements (id, batch_id, owner_id, predicate, args, category)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (stmt_id, batch_id, owner_id, predicate, Jsonb(args_json), category),
                )

    def insert_stmt_ref(self, stmt_id: str, position: int, ref_id: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO stmt_refs (stmt_id, position, ref_id)
                       VALUES (%s, %s, %s) ON CONFLICT DO NOTHING""",
                    (stmt_id, position, ref_id),
                )

    def insert_evidence(
        self,
        target_id: str,
        conf: float,
        src: Optional[str] = None,
        span: Optional[str] = None,
        residual: Optional[str] = None,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO evidence (target_id, conf, src, span, residual)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (target_id, conf, src, span, residual),
                )

    def insert_note(self, target_id: str, content: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO notes (target_id, content) VALUES (%s, %s)",
                    (target_id, content),
                )

    def upsert_vocab(
        self,
        word: str,
        category: str,
        arg_schema: Optional[str],
        definition: str,
        source: str = "llm_created",
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO vocab_registry (word, category, arg_schema, definition, source)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (word) DO UPDATE SET
                           usage_count = vocab_registry.usage_count + 1,
                           last_used = NOW()""",
                    (word, category, arg_schema, definition, source),
                )

    def query_statements(
        self,
        owner_id: str,
        predicate: Optional[str] = None,
        ref_id: Optional[str] = None,
        is_current: bool = True,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                query = "SELECT * FROM statements WHERE owner_id = %s"
                params: list = [owner_id]

                if is_current:
                    query += " AND is_current = TRUE"
                if predicate:
                    query += " AND predicate = %s"
                    params.append(predicate)
                if ref_id:
                    query += " AND id IN (SELECT stmt_id FROM stmt_refs WHERE ref_id = %s)"
                    params.append(ref_id)

                query += " ORDER BY created_at DESC LIMIT %s"
                params.append(limit)

                cur.execute(query, params)
                return [dict(row) for row in cur.fetchall()]

    def get_vocab_category(self, predicate: str) -> Optional[str]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT category FROM vocab_registry WHERE word = %s", (predicate,)
                )
                row = cur.fetchone()
                return row["category"] if row else None

    def insert_temporal_spec(
        self,
        stmt_id: str,
        time_type: str,
        anchor_turn: int,
        resolved_start: Optional[str] = None,
        resolved_end: Optional[str] = None,
        fuzzy_desc: Optional[str] = None,
        window_days: Optional[int] = None,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO temporal_specs
                       (stmt_id, time_type, resolved_start, resolved_end, fuzzy_desc, window_days, anchor_turn)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (stmt_id) DO UPDATE SET
                           time_type = EXCLUDED.time_type,
                           resolved_start = EXCLUDED.resolved_start,
                           resolved_end = EXCLUDED.resolved_end,
                           fuzzy_desc = EXCLUDED.fuzzy_desc,
                           window_days = EXCLUDED.window_days,
                           anchor_turn = EXCLUDED.anchor_turn""",
                    (stmt_id, time_type, resolved_start, resolved_end, fuzzy_desc, window_days, anchor_turn),
                )

    def mark_superseded(self, stmt_id: str, superseded_by: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE statements SET is_current = FALSE, superseded_by = %s WHERE id = %s",
                    (superseded_by, stmt_id),
                )

    def get_all_vocab_words(self) -> List[str]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT word FROM vocab_registry")
                return [row["word"] for row in cur.fetchall()]

    def query_recent_refs(
        self,
        owner_id: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT id, scope, ref_type, key, aliases
                       FROM refs WHERE owner_id = %s AND scope != 'self'
                       ORDER BY created_at DESC LIMIT %s""",
                    (owner_id, limit),
                )
                return [dict(row) for row in cur.fetchall()]

    def insert_coreference(
        self,
        source_expr: str,
        resolved_to: str,
        turn_id: int,
        confidence: float,
        method: Optional[str] = None,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO coreference (source_expr, resolved_to, turn_id, confidence, method)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (source_expr, resolved_to, turn_id, confidence, method),
                )

    def insert_coref_pending(
        self,
        source_expr: str,
        candidates: list,
        turn_id: int,
    ) -> None:
        _psycopg, _dict_row, sql, Jsonb = _load_postgres_modules()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO coref_pending (source_expr, candidates, turn_id)
                       VALUES (%s, %s, %s)""",
                    (source_expr, Jsonb(candidates), turn_id),
                )

    def close(self) -> None:
        pass  # Connections are context-managed per operation


# ══════════════════════════════════════════════════════════════════════
# Factory
# ══════════════════════════════════════════════════════════════════════

class STLStoreFactory:
    """Create an STL store backend from configuration."""

    @staticmethod
    def create(config) -> BaseSTLStore:
        """Create appropriate backend based on config.provider.

        Args:
            config: An object with ``provider`` and optionally ``dsn`` and
                    ``db_path`` attributes (e.g., STLStoreConfig).
        """
        provider = getattr(config, "provider", "sqlite")
        if provider == "postgres":
            dsn = getattr(config, "dsn", "")
            return PostgresSTLStore(dsn=dsn)
        elif provider == "sqlite":
            db_path = getattr(config, "db_path", ":memory:")
            return SQLiteSTLStore(db_path=db_path)
        else:
            raise ValueError(f"Unknown STL store provider: {provider!r}")
