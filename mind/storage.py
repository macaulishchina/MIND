"""Relational backing stores for history, owners, and owner-local subjects."""

from __future__ import annotations

import importlib
import json
import logging
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from mind.config.models import (
    HistoryRecord,
    MemoryOperation,
    OwnerContext,
    OwnerRecord,
    OwnerType,
    SubjectRecord,
)
from mind.config.schema import HistoryStoreConfig
from mind.ops_logger import ops
from mind.utils import generate_id, get_utc_now

logger = logging.getLogger(__name__)


def _load_postgres_modules() -> Tuple[Any, Any, Any, Any]:
    """Lazy-load Postgres modules so SQLite-only usage stays lightweight."""
    psycopg = importlib.import_module("psycopg")
    dict_row = importlib.import_module("psycopg.rows").dict_row
    sql = importlib.import_module("psycopg.sql")
    Jsonb = importlib.import_module("psycopg.types.json").Jsonb
    return psycopg, dict_row, sql, Jsonb


def _json_to_dict(value: Any) -> Dict[str, Any]:
    """Normalize JSON-like values from relational backends."""
    if value is None:
        return {}
    if isinstance(value, str):
        return json.loads(value)
    return dict(value)


def _build_history_record(
    memory_id: str,
    user_id: str,
    operation: MemoryOperation,
    old_content: Optional[str] = None,
    new_content: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> HistoryRecord:
    """Construct a history record with common defaults."""
    return HistoryRecord(
        id=generate_id(),
        memory_id=memory_id,
        user_id=user_id,
        operation=operation,
        old_content=old_content,
        new_content=new_content,
        timestamp=get_utc_now(),
        metadata=metadata or {},
    )


def _row_to_history_record(
    row: Dict[str, Any],
    metadata_value: Any,
) -> HistoryRecord:
    """Convert a row dict into a ``HistoryRecord``."""
    timestamp = row["timestamp"]
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp)

    return HistoryRecord(
        id=row["id"],
        memory_id=row["memory_id"],
        user_id=row["user_id"],
        operation=MemoryOperation(row["operation"]),
        old_content=row["old_content"],
        new_content=row["new_content"],
        timestamp=timestamp,
        metadata=_json_to_dict(metadata_value),
    )


def _row_to_owner_record(row: Dict[str, Any]) -> OwnerRecord:
    """Convert a row dict into an ``OwnerRecord``."""
    created_at = row["created_at"]
    last_seen_at = row["last_seen_at"]
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    if isinstance(last_seen_at, str):
        last_seen_at = datetime.fromisoformat(last_seen_at)

    return OwnerRecord(
        owner_id=row["owner_id"],
        owner_type=OwnerType(row["owner_type"]),
        external_user_id=row.get("external_user_id"),
        anonymous_session_id=row.get("anonymous_session_id"),
        display_name=row.get("display_name"),
        channel=row.get("channel"),
        created_at=created_at,
        last_seen_at=last_seen_at,
        metadata=_json_to_dict(row.get("metadata")),
    )


def _row_to_subject_record(row: Dict[str, Any]) -> SubjectRecord:
    """Convert a row dict into a ``SubjectRecord``."""
    created_at = row["created_at"]
    updated_at = row["updated_at"]
    if isinstance(created_at, str):
        created_at = datetime.fromisoformat(created_at)
    if isinstance(updated_at, str):
        updated_at = datetime.fromisoformat(updated_at)

    return SubjectRecord(
        owner_id=row["owner_id"],
        subject_ref=row["subject_ref"],
        relation_type=row["relation_type"],
        display_name=row.get("display_name"),
        normalized_name=row.get("normalized_name"),
        is_named=bool(row.get("is_named")),
        created_at=created_at,
        updated_at=updated_at,
        aliases=_json_to_dict(row.get("aliases")),
    )


class BaseHistoryStore(ABC):
    """Abstract base for relational backing stores."""

    @abstractmethod
    def add_record(
        self,
        memory_id: str,
        user_id: str,
        operation: MemoryOperation,
        old_content: Optional[str] = None,
        new_content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HistoryRecord:
        """Persist a memory history record."""

    @abstractmethod
    def get_history(self, memory_id: str) -> List[HistoryRecord]:
        """Return ordered history records for a memory."""

    @abstractmethod
    def resolve_owner(self, context: OwnerContext) -> OwnerRecord:
        """Resolve or create an owner from business-facing identity context."""

    @abstractmethod
    def get_or_create_named_subject(
        self,
        owner_id: str,
        relation_type: str,
        display_name: str,
        normalized_name: str,
        aliases: Optional[Dict[str, Any]] = None,
    ) -> SubjectRecord:
        """Resolve or create a named owner-local subject."""

    @abstractmethod
    def create_placeholder_subject(
        self,
        owner_id: str,
        relation_type: str,
        aliases: Optional[Dict[str, Any]] = None,
    ) -> SubjectRecord:
        """Create a new unnamed owner-local placeholder subject."""

    def close(self) -> None:
        """Release any backend resources."""


class SQLiteManager(BaseHistoryStore):
    """SQLite-backed relational store for history, owners, and subjects."""

    owners_table = "owners"
    subjects_table = "owner_subjects"

    def __init__(self, config: HistoryStoreConfig) -> None:
        self.db_path = config.db_path
        self.table_name = config.table_name
        self._local = threading.local()
        self._ensure_table()

    def _get_conn(self) -> sqlite3.Connection:
        """Return a per-thread SQLite connection."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            self._local.conn = conn
        return conn

    def _ensure_tables(self) -> None:
        conn = self._get_conn()
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                id           TEXT PRIMARY KEY,
                memory_id    TEXT NOT NULL,
                user_id      TEXT NOT NULL,
                operation    TEXT NOT NULL,
                old_content  TEXT,
                new_content  TEXT,
                timestamp    TEXT NOT NULL,
                metadata     TEXT DEFAULT '{{}}'
            )
            """
        )
        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{self.table_name}_memory_id
            ON {self.table_name} (memory_id)
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.owners_table} (
                owner_id              TEXT PRIMARY KEY,
                owner_type            TEXT NOT NULL,
                external_user_id      TEXT UNIQUE,
                anonymous_session_id  TEXT UNIQUE,
                display_name          TEXT,
                channel               TEXT,
                created_at            TEXT NOT NULL,
                last_seen_at          TEXT NOT NULL,
                metadata              TEXT DEFAULT '{{}}'
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.subjects_table} (
                owner_id          TEXT NOT NULL,
                subject_ref       TEXT NOT NULL,
                relation_type     TEXT NOT NULL,
                display_name      TEXT,
                normalized_name   TEXT,
                is_named          INTEGER NOT NULL DEFAULT 0,
                created_at        TEXT NOT NULL,
                updated_at        TEXT NOT NULL,
                aliases           TEXT DEFAULT '{{}}',
                PRIMARY KEY (owner_id, subject_ref)
            )
            """
        )
        conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{self.subjects_table}_owner_relation
            ON {self.subjects_table} (owner_id, relation_type)
            """
        )
        conn.commit()

    def _ensure_table(self) -> None:
        """Backward-compatible singular entry point."""
        self._ensure_tables()

    def add_record(
        self,
        memory_id: str,
        user_id: str,
        operation: MemoryOperation,
        old_content: Optional[str] = None,
        new_content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HistoryRecord:
        """Record a memory operation in history."""
        record = _build_history_record(
            memory_id=memory_id,
            user_id=user_id,
            operation=operation,
            old_content=old_content,
            new_content=new_content,
            metadata=metadata,
        )

        t0 = time.perf_counter()
        conn = self._get_conn()
        conn.execute(
            f"""
            INSERT INTO {self.table_name}
                (id, memory_id, user_id, operation, old_content, new_content,
                 timestamp, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.memory_id,
                record.user_id,
                record.operation.value,
                record.old_content,
                record.new_content,
                record.timestamp.isoformat(),
                json.dumps(record.metadata),
            ),
        )
        conn.commit()
        elapsed = time.perf_counter() - t0

        ops.db_op(
            "INSERT", self.table_name, self.db_path, elapsed,
            detail=f"{operation.value} | mem={memory_id}",
        )
        return record

    def get_history(self, memory_id: str) -> List[HistoryRecord]:
        """Get all history records for a given memory, ordered by time."""
        t0 = time.perf_counter()
        conn = self._get_conn()
        cursor = conn.execute(
            f"""
            SELECT id, memory_id, user_id, operation, old_content,
                   new_content, timestamp, metadata
            FROM {self.table_name}
            WHERE memory_id = ?
            ORDER BY timestamp ASC
            """,
            (memory_id,),
        )
        records = [
            _row_to_history_record(dict(row), row["metadata"])
            for row in cursor.fetchall()
        ]
        elapsed = time.perf_counter() - t0

        ops.db_op(
            "SELECT", self.table_name, self.db_path, elapsed,
            detail=f"mem={memory_id}", rows=len(records),
        )
        return records

    def resolve_owner(self, context: OwnerContext) -> OwnerRecord:
        """Resolve or create a durable owner record."""
        if bool(context.external_user_id) == bool(context.anonymous_session_id):
            raise ValueError(
                "OwnerContext must provide exactly one of external_user_id "
                "or anonymous_session_id"
            )

        owner_type = (
            OwnerType.KNOWN
            if context.external_user_id
            else OwnerType.ANONYMOUS
        )
        lookup_field = (
            "external_user_id"
            if context.external_user_id
            else "anonymous_session_id"
        )
        lookup_value = (
            context.external_user_id
            if context.external_user_id
            else context.anonymous_session_id
        )
        now = get_utc_now()
        conn = self._get_conn()
        row = conn.execute(
            f"SELECT * FROM {self.owners_table} WHERE {lookup_field} = ?",
            (lookup_value,),
        ).fetchone()

        if row is None:
            owner = OwnerRecord(
                owner_id=generate_id(),
                owner_type=owner_type,
                external_user_id=context.external_user_id,
                anonymous_session_id=context.anonymous_session_id,
                display_name=context.display_name,
                channel=context.channel,
                created_at=now,
                last_seen_at=now,
                metadata=context.metadata,
            )
            conn.execute(
                f"""
                INSERT INTO {self.owners_table}
                    (owner_id, owner_type, external_user_id, anonymous_session_id,
                     display_name, channel, created_at, last_seen_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    owner.owner_id,
                    owner.owner_type.value,
                    owner.external_user_id,
                    owner.anonymous_session_id,
                    owner.display_name,
                    owner.channel,
                    owner.created_at.isoformat(),
                    owner.last_seen_at.isoformat(),
                    json.dumps(owner.metadata),
                ),
            )
            conn.commit()
            return owner

        updates = {
            "display_name": context.display_name or row["display_name"],
            "channel": context.channel or row["channel"],
            "last_seen_at": now.isoformat(),
            "metadata": json.dumps({
                **_json_to_dict(row["metadata"]),
                **(context.metadata or {}),
            }),
        }
        conn.execute(
            f"""
            UPDATE {self.owners_table}
            SET display_name = ?, channel = ?, last_seen_at = ?, metadata = ?
            WHERE owner_id = ?
            """,
            (
                updates["display_name"],
                updates["channel"],
                updates["last_seen_at"],
                updates["metadata"],
                row["owner_id"],
            ),
        )
        conn.commit()

        return _row_to_owner_record(
            {
                **dict(row),
                **updates,
            }
        )

    def get_or_create_named_subject(
        self,
        owner_id: str,
        relation_type: str,
        display_name: str,
        normalized_name: str,
        aliases: Optional[Dict[str, Any]] = None,
    ) -> SubjectRecord:
        """Resolve or create a named owner-local subject."""
        subject_ref = f"{relation_type}:{normalized_name}"
        now = get_utc_now()
        conn = self._get_conn()
        row = conn.execute(
            f"""
            SELECT * FROM {self.subjects_table}
            WHERE owner_id = ? AND subject_ref = ?
            """,
            (owner_id, subject_ref),
        ).fetchone()

        if row is None:
            subject = SubjectRecord(
                owner_id=owner_id,
                subject_ref=subject_ref,
                relation_type=relation_type,
                display_name=display_name,
                normalized_name=normalized_name,
                is_named=True,
                created_at=now,
                updated_at=now,
                aliases=aliases or {},
            )
            conn.execute(
                f"""
                INSERT INTO {self.subjects_table}
                    (owner_id, subject_ref, relation_type, display_name,
                     normalized_name, is_named, created_at, updated_at, aliases)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    subject.owner_id,
                    subject.subject_ref,
                    subject.relation_type,
                    subject.display_name,
                    subject.normalized_name,
                    1,
                    subject.created_at.isoformat(),
                    subject.updated_at.isoformat(),
                    json.dumps(subject.aliases),
                ),
            )
            conn.commit()
            return subject

        merged_aliases = {
            **_json_to_dict(row["aliases"]),
            **(aliases or {}),
        }
        display_name_value = display_name or row["display_name"]
        conn.execute(
            f"""
            UPDATE {self.subjects_table}
            SET display_name = ?, updated_at = ?, aliases = ?
            WHERE owner_id = ? AND subject_ref = ?
            """,
            (
                display_name_value,
                now.isoformat(),
                json.dumps(merged_aliases),
                owner_id,
                subject_ref,
            ),
        )
        conn.commit()
        return _row_to_subject_record(
            {
                **dict(row),
                "display_name": display_name_value,
                "updated_at": now.isoformat(),
                "aliases": json.dumps(merged_aliases),
            }
        )

    def create_placeholder_subject(
        self,
        owner_id: str,
        relation_type: str,
        aliases: Optional[Dict[str, Any]] = None,
    ) -> SubjectRecord:
        """Create a new owner-local unnamed placeholder subject."""
        conn = self._get_conn()
        cursor = conn.execute(
            f"""
            SELECT subject_ref
            FROM {self.subjects_table}
            WHERE owner_id = ? AND relation_type = ? AND is_named = 0
            """,
            (owner_id, relation_type),
        )
        max_index = 0
        for row in cursor.fetchall():
            ref = row["subject_ref"]
            if ref.startswith(f"{relation_type}:unknown_"):
                try:
                    max_index = max(max_index, int(ref.rsplit("_", 1)[-1]))
                except ValueError:
                    continue

        subject_ref = f"{relation_type}:unknown_{max_index + 1}"
        now = get_utc_now()
        subject = SubjectRecord(
            owner_id=owner_id,
            subject_ref=subject_ref,
            relation_type=relation_type,
            display_name=None,
            normalized_name=None,
            is_named=False,
            created_at=now,
            updated_at=now,
            aliases=aliases or {},
        )
        conn.execute(
            f"""
            INSERT INTO {self.subjects_table}
                (owner_id, subject_ref, relation_type, display_name,
                 normalized_name, is_named, created_at, updated_at, aliases)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                subject.owner_id,
                subject.subject_ref,
                subject.relation_type,
                subject.display_name,
                subject.normalized_name,
                0,
                subject.created_at.isoformat(),
                subject.updated_at.isoformat(),
                json.dumps(subject.aliases),
            ),
        )
        conn.commit()
        return subject

    def close(self) -> None:
        """Close the current thread's database connection."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None


class PostgresHistoryManager(BaseHistoryStore):
    """Postgres-backed relational store for history, owners, and subjects."""

    owners_table = "owners"
    subjects_table = "owner_subjects"

    def __init__(self, config: HistoryStoreConfig) -> None:
        if not config.dsn:
            raise ValueError("history_store.dsn is required for provider='postgres'")
        self.dsn = config.dsn
        self.table_name = config.table_name
        self._ensure_table()

    def _connect(self):
        psycopg, dict_row, _sql, _Jsonb = _load_postgres_modules()
        return psycopg.connect(self.dsn, autocommit=True, row_factory=dict_row)

    def _ensure_tables(self) -> None:
        _psycopg, _dict_row, sql, _Jsonb = _load_postgres_modules()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        CREATE TABLE IF NOT EXISTS {} (
                            id           TEXT PRIMARY KEY,
                            memory_id    TEXT NOT NULL,
                            user_id      TEXT NOT NULL,
                            operation    TEXT NOT NULL,
                            old_content  TEXT,
                            new_content  TEXT,
                            timestamp    TIMESTAMPTZ NOT NULL,
                            metadata     JSONB NOT NULL DEFAULT '{{}}'::jsonb
                        )
                        """
                    ).format(sql.Identifier(self.table_name))
                )
                cur.execute(
                    sql.SQL(
                        """
                        CREATE INDEX IF NOT EXISTS {} ON {} (memory_id)
                        """
                    ).format(
                        sql.Identifier(f"idx_{self.table_name}_memory_id"),
                        sql.Identifier(self.table_name),
                    )
                )
                cur.execute(
                    sql.SQL(
                        """
                        CREATE TABLE IF NOT EXISTS {} (
                            owner_id             TEXT PRIMARY KEY,
                            owner_type           TEXT NOT NULL,
                            external_user_id     TEXT UNIQUE,
                            anonymous_session_id TEXT UNIQUE,
                            display_name         TEXT,
                            channel              TEXT,
                            created_at           TIMESTAMPTZ NOT NULL,
                            last_seen_at         TIMESTAMPTZ NOT NULL,
                            metadata             JSONB NOT NULL DEFAULT '{{}}'::jsonb
                        )
                        """
                    ).format(sql.Identifier(self.owners_table))
                )
                cur.execute(
                    sql.SQL(
                        """
                        CREATE TABLE IF NOT EXISTS {} (
                            owner_id        TEXT NOT NULL,
                            subject_ref     TEXT NOT NULL,
                            relation_type   TEXT NOT NULL,
                            display_name    TEXT,
                            normalized_name TEXT,
                            is_named        BOOLEAN NOT NULL DEFAULT FALSE,
                            created_at      TIMESTAMPTZ NOT NULL,
                            updated_at      TIMESTAMPTZ NOT NULL,
                            aliases         JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            PRIMARY KEY (owner_id, subject_ref)
                        )
                        """
                    ).format(sql.Identifier(self.subjects_table))
                )
                cur.execute(
                    sql.SQL(
                        """
                        CREATE INDEX IF NOT EXISTS {} ON {} (owner_id, relation_type)
                        """
                    ).format(
                        sql.Identifier(f"idx_{self.subjects_table}_owner_relation"),
                        sql.Identifier(self.subjects_table),
                    )
                )

    def _ensure_table(self) -> None:
        """Backward-compatible singular entry point."""
        self._ensure_tables()

    def add_record(
        self,
        memory_id: str,
        user_id: str,
        operation: MemoryOperation,
        old_content: Optional[str] = None,
        new_content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HistoryRecord:
        """Record a memory operation in Postgres."""
        _psycopg, _dict_row, sql, Jsonb = _load_postgres_modules()
        record = _build_history_record(
            memory_id=memory_id,
            user_id=user_id,
            operation=operation,
            old_content=old_content,
            new_content=new_content,
            metadata=metadata,
        )

        t0 = time.perf_counter()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        INSERT INTO {}
                            (id, memory_id, user_id, operation, old_content,
                             new_content, timestamp, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """
                    ).format(sql.Identifier(self.table_name)),
                    (
                        record.id,
                        record.memory_id,
                        record.user_id,
                        record.operation.value,
                        record.old_content,
                        record.new_content,
                        record.timestamp,
                        Jsonb(record.metadata),
                    ),
                )
        elapsed = time.perf_counter() - t0

        ops.db_op(
            "INSERT", self.table_name, self.dsn, elapsed,
            detail=f"{operation.value} | mem={memory_id}",
        )
        return record

    def get_history(self, memory_id: str) -> List[HistoryRecord]:
        """Get all history records for a given memory, ordered by time."""
        _psycopg, _dict_row, sql, _Jsonb = _load_postgres_modules()
        t0 = time.perf_counter()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        SELECT id, memory_id, user_id, operation, old_content,
                               new_content, timestamp, metadata
                        FROM {}
                        WHERE memory_id = %s
                        ORDER BY timestamp ASC
                        """
                    ).format(sql.Identifier(self.table_name)),
                    (memory_id,),
                )
                rows = cur.fetchall()
        records = [
            _row_to_history_record(row, row["metadata"])
            for row in rows
        ]
        elapsed = time.perf_counter() - t0

        ops.db_op(
            "SELECT", self.table_name, self.dsn, elapsed,
            detail=f"mem={memory_id}", rows=len(records),
        )
        return records

    def resolve_owner(self, context: OwnerContext) -> OwnerRecord:
        """Resolve or create a durable owner record."""
        if bool(context.external_user_id) == bool(context.anonymous_session_id):
            raise ValueError(
                "OwnerContext must provide exactly one of external_user_id "
                "or anonymous_session_id"
            )

        _psycopg, _dict_row, sql, Jsonb = _load_postgres_modules()
        owner_type = (
            OwnerType.KNOWN
            if context.external_user_id
            else OwnerType.ANONYMOUS
        )
        lookup_field = (
            "external_user_id"
            if context.external_user_id
            else "anonymous_session_id"
        )
        lookup_value = (
            context.external_user_id
            if context.external_user_id
            else context.anonymous_session_id
        )
        now = get_utc_now()

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("SELECT * FROM {} WHERE {} = %s").format(
                        sql.Identifier(self.owners_table),
                        sql.Identifier(lookup_field),
                    ),
                    (lookup_value,),
                )
                row = cur.fetchone()

                if row is None:
                    owner = OwnerRecord(
                        owner_id=generate_id(),
                        owner_type=owner_type,
                        external_user_id=context.external_user_id,
                        anonymous_session_id=context.anonymous_session_id,
                        display_name=context.display_name,
                        channel=context.channel,
                        created_at=now,
                        last_seen_at=now,
                        metadata=context.metadata,
                    )
                    cur.execute(
                        sql.SQL(
                            """
                            INSERT INTO {}
                                (owner_id, owner_type, external_user_id,
                                 anonymous_session_id, display_name, channel,
                                 created_at, last_seen_at, metadata)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """
                        ).format(sql.Identifier(self.owners_table)),
                        (
                            owner.owner_id,
                            owner.owner_type.value,
                            owner.external_user_id,
                            owner.anonymous_session_id,
                            owner.display_name,
                            owner.channel,
                            owner.created_at,
                            owner.last_seen_at,
                            Jsonb(owner.metadata),
                        ),
                    )
                    return owner

                merged_metadata = {
                    **_json_to_dict(row.get("metadata")),
                    **(context.metadata or {}),
                }
                updated_row = {
                    **row,
                    "display_name": context.display_name or row.get("display_name"),
                    "channel": context.channel or row.get("channel"),
                    "last_seen_at": now,
                    "metadata": merged_metadata,
                }
                cur.execute(
                    sql.SQL(
                        """
                        UPDATE {}
                        SET display_name = %s, channel = %s, last_seen_at = %s,
                            metadata = %s
                        WHERE owner_id = %s
                        """
                    ).format(sql.Identifier(self.owners_table)),
                    (
                        updated_row["display_name"],
                        updated_row["channel"],
                        updated_row["last_seen_at"],
                        Jsonb(updated_row["metadata"]),
                        row["owner_id"],
                    ),
                )
                return _row_to_owner_record(updated_row)

    def get_or_create_named_subject(
        self,
        owner_id: str,
        relation_type: str,
        display_name: str,
        normalized_name: str,
        aliases: Optional[Dict[str, Any]] = None,
    ) -> SubjectRecord:
        """Resolve or create a named owner-local subject."""
        _psycopg, _dict_row, sql, Jsonb = _load_postgres_modules()
        subject_ref = f"{relation_type}:{normalized_name}"
        now = get_utc_now()

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        SELECT * FROM {}
                        WHERE owner_id = %s AND subject_ref = %s
                        """
                    ).format(sql.Identifier(self.subjects_table)),
                    (owner_id, subject_ref),
                )
                row = cur.fetchone()

                if row is None:
                    subject = SubjectRecord(
                        owner_id=owner_id,
                        subject_ref=subject_ref,
                        relation_type=relation_type,
                        display_name=display_name,
                        normalized_name=normalized_name,
                        is_named=True,
                        created_at=now,
                        updated_at=now,
                        aliases=aliases or {},
                    )
                    cur.execute(
                        sql.SQL(
                            """
                            INSERT INTO {}
                                (owner_id, subject_ref, relation_type, display_name,
                                 normalized_name, is_named, created_at, updated_at,
                                 aliases)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            """
                        ).format(sql.Identifier(self.subjects_table)),
                        (
                            subject.owner_id,
                            subject.subject_ref,
                            subject.relation_type,
                            subject.display_name,
                            subject.normalized_name,
                            True,
                            subject.created_at,
                            subject.updated_at,
                            Jsonb(subject.aliases),
                        ),
                    )
                    return subject

                merged_aliases = {
                    **_json_to_dict(row.get("aliases")),
                    **(aliases or {}),
                }
                display_name_value = display_name or row.get("display_name")
                updated_row = {
                    **row,
                    "display_name": display_name_value,
                    "updated_at": now,
                    "aliases": merged_aliases,
                }
                cur.execute(
                    sql.SQL(
                        """
                        UPDATE {}
                        SET display_name = %s, updated_at = %s, aliases = %s
                        WHERE owner_id = %s AND subject_ref = %s
                        """
                    ).format(sql.Identifier(self.subjects_table)),
                    (
                        display_name_value,
                        now,
                        Jsonb(merged_aliases),
                        owner_id,
                        subject_ref,
                    ),
                )
                return _row_to_subject_record(updated_row)

    def create_placeholder_subject(
        self,
        owner_id: str,
        relation_type: str,
        aliases: Optional[Dict[str, Any]] = None,
    ) -> SubjectRecord:
        """Create a new owner-local unnamed placeholder subject."""
        _psycopg, _dict_row, sql, Jsonb = _load_postgres_modules()
        now = get_utc_now()

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        SELECT subject_ref
                        FROM {}
                        WHERE owner_id = %s AND relation_type = %s AND is_named = FALSE
                        """
                    ).format(sql.Identifier(self.subjects_table)),
                    (owner_id, relation_type),
                )
                max_index = 0
                for row in cur.fetchall():
                    ref = row["subject_ref"]
                    if ref.startswith(f"{relation_type}:unknown_"):
                        try:
                            max_index = max(max_index, int(ref.rsplit("_", 1)[-1]))
                        except ValueError:
                            continue

                subject_ref = f"{relation_type}:unknown_{max_index + 1}"
                subject = SubjectRecord(
                    owner_id=owner_id,
                    subject_ref=subject_ref,
                    relation_type=relation_type,
                    display_name=None,
                    normalized_name=None,
                    is_named=False,
                    created_at=now,
                    updated_at=now,
                    aliases=aliases or {},
                )
                cur.execute(
                    sql.SQL(
                        """
                        INSERT INTO {}
                            (owner_id, subject_ref, relation_type, display_name,
                             normalized_name, is_named, created_at, updated_at, aliases)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """
                    ).format(sql.Identifier(self.subjects_table)),
                    (
                        subject.owner_id,
                        subject.subject_ref,
                        subject.relation_type,
                        subject.display_name,
                        subject.normalized_name,
                        False,
                        subject.created_at,
                        subject.updated_at,
                        Jsonb(subject.aliases),
                    ),
                )
                return subject


class HistoryStoreFactory:
    """Create a relational backing store from configuration."""

    _provider_map = {
        "sqlite": SQLiteManager,
        "postgres": PostgresHistoryManager,
    }

    @classmethod
    def create(cls, config: HistoryStoreConfig) -> BaseHistoryStore:
        provider = config.provider.lower()
        if provider not in cls._provider_map:
            raise ValueError(
                f"Unsupported history store provider: {provider}. "
                f"Available: {list(cls._provider_map.keys())}"
            )
        return cls._provider_map[provider](config)
