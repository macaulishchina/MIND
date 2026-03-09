"""Append-only SQLite-backed memory storage."""

from __future__ import annotations

import json
import sqlite3
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol, TypeAlias

from .schema import ensure_valid_object


class StoreError(RuntimeError):
    """Raised when a store operation cannot be completed safely."""


class MemoryStore(Protocol):
    """Minimal store contract shared by Phase B/C kernel code."""

    def insert_object(self, obj: dict[str, Any]) -> None: ...

    def insert_objects(self, objects: Iterable[dict[str, Any]]) -> None: ...

    def has_object(self, object_id: str) -> bool: ...

    def versions_for_object(self, object_id: str) -> list[int]: ...

    def read_object(self, object_id: str, version: int | None = None) -> dict[str, Any]: ...

    def iter_objects(self) -> list[dict[str, Any]]: ...

    def raw_records_for_episode(self, episode_id: str) -> list[dict[str, Any]]: ...


MemoryStoreContextManager: TypeAlias = AbstractContextManager[MemoryStore]
MemoryStoreFactory: TypeAlias = Callable[[Path], MemoryStoreContextManager]


class SQLiteMemoryStore:
    """A minimal append-only memory store for Phase B."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "SQLiteMemoryStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _init_schema(self) -> None:
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS object_versions (
                object_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                type TEXT NOT NULL,
                content_json TEXT NOT NULL,
                source_refs_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,
                priority REAL NOT NULL,
                metadata_json TEXT NOT NULL,
                inserted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (object_id, version)
            )
            """
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_object_versions_object_id ON object_versions(object_id)"
        )
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_object_versions_type ON object_versions(type)"
        )
        self.connection.commit()

    def insert_object(self, obj: dict[str, Any]) -> None:
        ensure_valid_object(obj)
        self._validate_and_insert(obj)
        self.connection.commit()

    def insert_objects(self, objects: Iterable[dict[str, Any]]) -> None:
        """Atomically insert a batch of objects.

        Either all objects are persisted or none are.  Pre-validates every
        object *before* touching the database so that a validation failure
        in the Nth object does not leave the first N-1 committed.
        """
        obj_list = list(objects)
        for obj in obj_list:
            ensure_valid_object(obj)
        try:
            for obj in obj_list:
                self._validate_and_insert(obj)
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_and_insert(self, obj: dict[str, Any]) -> None:
        """Check store-level invariants and execute the INSERT.

        Does **not** commit — the caller is responsible for commit/rollback.
        """
        object_id = obj["id"]
        version = obj["version"]
        existing_versions = self.versions_for_object(object_id)

        if version == 1 and existing_versions:
            raise StoreError(f"object '{object_id}' version 1 already exists")
        if version > 1 and not existing_versions:
            raise StoreError(f"object '{object_id}' version {version} missing prior versions")
        if version > 1 and version != max(existing_versions) + 1:
            raise StoreError(f"object '{object_id}' version chain must be contiguous")

        # I-2 fix: enforce type consistency across versions
        if version > 1:
            prev = self.read_object(object_id, max(existing_versions))
            if prev["type"] != obj["type"]:
                raise StoreError(
                    f"object '{object_id}' type changed from "
                    f"'{prev['type']}' to '{obj['type']}' across versions"
                )

        missing_refs = [ref for ref in obj["source_refs"] if not self.has_object(ref)]
        if missing_refs:
            raise StoreError(f"object '{object_id}' has dangling source refs: {missing_refs}")

        try:
            self.connection.execute(
                """
                INSERT INTO object_versions (
                    object_id,
                    version,
                    type,
                    content_json,
                    source_refs_json,
                    created_at,
                    updated_at,
                    status,
                    priority,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    object_id,
                    version,
                    obj["type"],
                    json.dumps(obj["content"], ensure_ascii=True, sort_keys=True),
                    json.dumps(obj["source_refs"], ensure_ascii=True),
                    obj["created_at"],
                    obj["updated_at"],
                    obj["status"],
                    float(obj["priority"]),
                    json.dumps(obj["metadata"], ensure_ascii=True, sort_keys=True),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise StoreError(str(exc)) from exc

    def has_object(self, object_id: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM object_versions WHERE object_id = ? LIMIT 1", (object_id,)
        ).fetchone()
        return row is not None

    def versions_for_object(self, object_id: str) -> list[int]:
        rows = self.connection.execute(
            "SELECT version FROM object_versions WHERE object_id = ? ORDER BY version ASC",
            (object_id,),
        ).fetchall()
        return [int(row["version"]) for row in rows]

    def read_object(self, object_id: str, version: int | None = None) -> dict[str, Any]:
        if version is None:
            row = self.connection.execute(
                """
                SELECT * FROM object_versions
                WHERE object_id = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (object_id,),
            ).fetchone()
        else:
            row = self.connection.execute(
                "SELECT * FROM object_versions WHERE object_id = ? AND version = ?",
                (object_id, version),
            ).fetchone()

        if row is None:
            raise StoreError(f"object '{object_id}' not found")
        return self._decode_row(row)

    def iter_objects(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT * FROM object_versions
            ORDER BY inserted_at ASC, object_id ASC, version ASC
            """
        ).fetchall()
        return [self._decode_row(row) for row in rows]

    def raw_records_for_episode(self, episode_id: str) -> list[dict[str, Any]]:
        records = [
            obj
            for obj in self.iter_objects()
            if obj["type"] == "RawRecord" and obj["metadata"]["episode_id"] == episode_id
        ]
        return sorted(records, key=lambda item: item["metadata"]["timestamp_order"])

    @staticmethod
    def _decode_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["object_id"],
            "type": row["type"],
            "content": json.loads(row["content_json"]),
            "source_refs": json.loads(row["source_refs_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "version": int(row["version"]),
            "status": row["status"],
            "priority": float(row["priority"]),
            "metadata": json.loads(row["metadata_json"]),
        }
