"""History-store implementations and factory."""

import importlib
import json
import logging
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from mind.config.models import HistoryRecord, MemoryOperation
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
    if isinstance(metadata_value, str):
        metadata = json.loads(metadata_value)
    elif metadata_value is None:
        metadata = {}
    else:
        metadata = dict(metadata_value)

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
        metadata=metadata,
    )


class BaseHistoryStore(ABC):
    """Abstract base for history stores."""

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

    def close(self) -> None:
        """Release any backend resources."""


class SQLiteManager(BaseHistoryStore):
    """Manages operation history for memories using SQLite."""

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
            self._local.conn = conn
        return conn

    def _ensure_table(self) -> None:
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
        conn.commit()
        logger.debug("History table ensured at %s", self.db_path)

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

    def close(self) -> None:
        """Close the current thread's database connection."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None


class PostgresHistoryManager(BaseHistoryStore):
    """Postgres-backed history tracking."""

    def __init__(self, config: HistoryStoreConfig) -> None:
        if not config.dsn:
            raise ValueError("history_store.dsn is required for provider='postgres'")
        self.dsn = config.dsn
        self.table_name = config.table_name
        self._ensure_table()

    def _connect(self):
        psycopg, dict_row, _sql, _Jsonb = _load_postgres_modules()
        return psycopg.connect(self.dsn, autocommit=True, row_factory=dict_row)

    def _ensure_table(self) -> None:
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


class HistoryStoreFactory:
    """Create a history-store backend from configuration."""

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
