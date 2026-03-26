"""SQLite-based history tracking for memory operations."""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from mind.config.models import HistoryRecord, MemoryOperation
from mind.config.schema import HistoryStoreConfig
from mind.utils import generate_id, get_utc_now

logger = logging.getLogger(__name__)


class SQLiteManager:
    """Manages operation history for memories using SQLite.

    Each ADD, UPDATE, or DELETE operation creates a history record so that
    the full lifecycle of any memory can be reconstructed.
    """

    def __init__(self, config: HistoryStoreConfig) -> None:
        self.db_path = config.db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._ensure_table()

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

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
        return record

    def get_history(self, memory_id: str) -> List[HistoryRecord]:
        """Get all history records for a given memory, ordered by time."""
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
        return records

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
