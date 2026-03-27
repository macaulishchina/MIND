"""SQLite-based history tracking for memory operations."""

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from mind.config.models import HistoryRecord, MemoryOperation
from mind.config.schema import HistoryStoreConfig
from mind.ops_logger import ops
from mind.utils import generate_id, get_utc_now

logger = logging.getLogger(__name__)


class SQLiteManager:
    """Manages operation history for memories using SQLite.

    Each ADD, UPDATE, or DELETE operation creates a history record so that
    the full lifecycle of any memory can be reconstructed.
    """

    def __init__(self, config: HistoryStoreConfig) -> None:
        self.db_path = config.db_path
        self._local = threading.local()
        self._ensure_table()

    # ------------------------------------------------------------------
    # Connection management (per-thread, thread-safe)
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        """Return a per-thread SQLite connection.

        Uses ``threading.local()`` so each thread gets its own connection,
        avoiding the ``sqlite3.ProgrammingError`` that occurs when a
        connection is used across threads.
        """
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def _ensure_table(self) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_history (
                id           TEXT PRIMARY KEY,
                memory_id    TEXT NOT NULL,
                user_id      TEXT NOT NULL,
                operation    TEXT NOT NULL,
                old_content  TEXT,
                new_content  TEXT,
                timestamp    TEXT NOT NULL,
                metadata     TEXT DEFAULT '{}'
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_history_memory_id
            ON memory_history (memory_id)
            """
        )
        conn.commit()
        logger.debug("History table ensured at %s", self.db_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
        record = HistoryRecord(
            id=generate_id(),
            memory_id=memory_id,
            user_id=user_id,
            operation=operation,
            old_content=old_content,
            new_content=new_content,
            timestamp=get_utc_now(),
            metadata=metadata or {},
        )

        t0 = time.perf_counter()
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO memory_history
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
            "INSERT", "memory_history", self.db_path, elapsed,
            detail=f"{operation.value} | mem={memory_id}",
        )
        return record

    def get_history(self, memory_id: str) -> List[HistoryRecord]:
        """Get all history records for a given memory, ordered by time."""
        t0 = time.perf_counter()
        conn = self._get_conn()
        cursor = conn.execute(
            """
            SELECT id, memory_id, user_id, operation, old_content,
                   new_content, timestamp, metadata
            FROM memory_history
            WHERE memory_id = ?
            ORDER BY timestamp ASC
            """,
            (memory_id,),
        )

        records = []
        for row in cursor.fetchall():
            records.append(
                HistoryRecord(
                    id=row["id"],
                    memory_id=row["memory_id"],
                    user_id=row["user_id"],
                    operation=MemoryOperation(row["operation"]),
                    old_content=row["old_content"],
                    new_content=row["new_content"],
                    timestamp=datetime.fromisoformat(row["timestamp"]),
                    metadata=json.loads(row["metadata"]),
                )
            )
        elapsed = time.perf_counter() - t0

        ops.db_op(
            "SELECT", "memory_history", self.db_path, elapsed,
            detail=f"mem={memory_id}", rows=len(records),
        )
        return records

    def close(self) -> None:
        """Close the current thread's database connection."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None
