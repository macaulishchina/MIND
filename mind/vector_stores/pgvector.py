"""Postgres + pgvector vector store implementation."""

from typing import Any, Dict, List, Optional, Sequence

from mind.vector_stores.base import BaseVectorStore


class PgVectorStore(BaseVectorStore):
    """Postgres-backed vector store with pgvector embeddings."""

    _payload_columns = (
        "user_id",
        "content",
        "hash",
        "metadata",
        "created_at",
        "updated_at",
        "confidence",
        "status",
        "source_context",
        "source_session_id",
        "version_of",
        "importance",
        "type",
    )

    def __init__(self, config) -> None:
        if not config.dsn:
            raise ValueError("vector_store.dsn is required for provider='pgvector'")
        self.config = config
        self.collection_name = config.collection_name

    @staticmethod
    def _load_modules():
        import psycopg
        from pgvector import Vector
        from pgvector.psycopg import register_vector
        from psycopg import sql
        from psycopg.rows import dict_row
        from psycopg.types.json import Jsonb

        return psycopg, Vector, register_vector, sql, dict_row, Jsonb

    def _connect(self, register_types: bool = True):
        psycopg, _Vector, register_vector, _sql, dict_row, _Jsonb = self._load_modules()
        conn = psycopg.connect(
            self.config.dsn,
            autocommit=True,
            row_factory=dict_row,
        )
        if register_types:
            register_vector(conn)
        return conn

    def create_collection(self, dimensions: int) -> None:
        """Create the table backing memory storage if it does not exist."""
        _psycopg, _Vector, register_vector, sql, _dict_row, _Jsonb = self._load_modules()
        with self._connect(register_types=False) as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
                register_vector(conn)
                cur.execute(
                    sql.SQL(
                        """
                        CREATE TABLE IF NOT EXISTS {} (
                            id                TEXT PRIMARY KEY,
                            embedding         VECTOR({}) NOT NULL,
                            user_id           TEXT NOT NULL,
                            content           TEXT NOT NULL,
                            hash              TEXT NOT NULL,
                            metadata          JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                            created_at        TIMESTAMPTZ,
                            updated_at        TIMESTAMPTZ,
                            confidence        DOUBLE PRECISION,
                            status            TEXT NOT NULL DEFAULT 'active',
                            source_context    TEXT,
                            source_session_id TEXT,
                            version_of        TEXT,
                            importance        DOUBLE PRECISION,
                            type              TEXT
                        )
                        """
                    ).format(
                        sql.Identifier(self.collection_name),
                        sql.SQL(str(dimensions)),
                    )
                )
                cur.execute(
                    sql.SQL(
                        """
                        CREATE INDEX IF NOT EXISTS {} ON {} (user_id, status)
                        """
                    ).format(
                        sql.Identifier(f"idx_{self.collection_name}_user_status"),
                        sql.Identifier(self.collection_name),
                    )
                )
                cur.execute(
                    sql.SQL(
                        """
                        CREATE INDEX IF NOT EXISTS {} ON {} (version_of)
                        """
                    ).format(
                        sql.Identifier(f"idx_{self.collection_name}_version_of"),
                        sql.Identifier(self.collection_name),
                    )
                )

    def _insert(
        self,
        id: str,
        vector: List[float],
        payload: Dict[str, Any],
    ) -> None:
        _psycopg, Vector, _register_vector, sql, _dict_row, Jsonb = self._load_modules()
        row = self._payload_to_row(payload)
        columns = ["id", "embedding", *self._payload_columns]
        values = [id, Vector(vector), *[row[column] for column in self._payload_columns]]
        placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in columns)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                        sql.Identifier(self.collection_name),
                        sql.SQL(", ").join(sql.Identifier(c) for c in columns),
                        placeholders,
                    ),
                    self._adapt_params(values, Jsonb),
                )

    def _search(
        self,
        query_vector: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        _psycopg, Vector, _register_vector, sql, _dict_row, _Jsonb = self._load_modules()
        where_clause, params = self._build_filter(filters, sql)
        vector_value = Vector(query_vector)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        SELECT id, {}, 1 - (embedding <=> %s) AS score
                        FROM {}
                        {}
                        ORDER BY embedding <=> %s
                        LIMIT %s
                        """
                    ).format(
                        sql.SQL(", ").join(sql.Identifier(c) for c in self._payload_columns),
                        sql.Identifier(self.collection_name),
                        where_clause,
                    ),
                    [vector_value, *params, vector_value, limit],
                )
                rows = cur.fetchall()

        return [
            {
                "id": row["id"],
                "score": row["score"],
                "payload": self._row_to_payload(row),
            }
            for row in rows
        ]

    def _get(self, id: str) -> Optional[Dict[str, Any]]:
        _psycopg, _Vector, _register_vector, sql, _dict_row, _Jsonb = self._load_modules()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        SELECT id, {}
                        FROM {}
                        WHERE id = %s
                        """
                    ).format(
                        sql.SQL(", ").join(sql.Identifier(c) for c in self._payload_columns),
                        sql.Identifier(self.collection_name),
                    ),
                    (id,),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return {"id": row["id"], "payload": self._row_to_payload(row)}

    def _list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        _psycopg, _Vector, _register_vector, sql, _dict_row, _Jsonb = self._load_modules()
        where_clause, params = self._build_filter(filters, sql)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        SELECT id, {}
                        FROM {}
                        {}
                        ORDER BY created_at ASC NULLS LAST, id ASC
                        LIMIT %s
                        """
                    ).format(
                        sql.SQL(", ").join(sql.Identifier(c) for c in self._payload_columns),
                        sql.Identifier(self.collection_name),
                        where_clause,
                    ),
                    [*params, limit],
                )
                rows = cur.fetchall()

        return [
            {"id": row["id"], "payload": self._row_to_payload(row)}
            for row in rows
        ]

    def _update(
        self,
        id: str,
        vector: Optional[List[float]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        _psycopg, Vector, _register_vector, sql, _dict_row, Jsonb = self._load_modules()
        assignments = []
        params: List[Any] = []

        if vector is not None:
            assignments.append(sql.SQL("{} = {}").format(
                sql.Identifier("embedding"),
                sql.Placeholder(),
            ))
            params.append(Vector(vector))

        if payload is not None:
            row = self._payload_to_row(payload, partial=True)
            for column, value in row.items():
                assignments.append(sql.SQL("{} = {}").format(
                    sql.Identifier(column),
                    sql.Placeholder(),
                ))
                params.append(Jsonb(value) if column == "metadata" else value)

        if not assignments:
            return

        params.append(id)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("UPDATE {} SET {} WHERE id = %s").format(
                        sql.Identifier(self.collection_name),
                        sql.SQL(", ").join(assignments),
                    ),
                    params,
                )

    def _delete(self, id: str) -> None:
        _psycopg, _Vector, _register_vector, sql, _dict_row, _Jsonb = self._load_modules()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("DELETE FROM {} WHERE id = %s").format(
                        sql.Identifier(self.collection_name),
                    ),
                    (id,),
                )

    @classmethod
    def _payload_to_row(
        cls,
        payload: Dict[str, Any],
        partial: bool = False,
    ) -> Dict[str, Any]:
        """Map vector-store payload fields to relational columns."""
        row: Dict[str, Any] = {}
        for column in cls._payload_columns:
            if partial and column not in payload:
                continue
            if column == "metadata":
                row[column] = payload.get(column, {})
            else:
                row[column] = payload.get(column)
        return row

    @classmethod
    def _row_to_payload(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        """Map relational columns back to the vector-store payload shape."""
        payload = {}
        for column in cls._payload_columns:
            payload[column] = row.get(column)
        payload["metadata"] = payload.get("metadata") or {}
        return payload

    @staticmethod
    def _adapt_params(values: Sequence[Any], Jsonb) -> List[Any]:
        """Adapt payload parameter types for psycopg."""
        adapted = []
        for value in values:
            if isinstance(value, dict):
                adapted.append(Jsonb(value))
            else:
                adapted.append(value)
        return adapted

    @classmethod
    def _build_filter(cls, filters: Optional[Dict[str, Any]], sql):
        """Build a simple equality filter clause."""
        if not filters:
            return sql.SQL(""), []

        clauses = []
        params = []
        allowed = set(cls._payload_columns)
        for key, value in filters.items():
            if key not in allowed:
                raise ValueError(f"Unsupported pgvector filter key: {key}")
            clauses.append(
                sql.SQL("{} = {}").format(
                    sql.Identifier(key),
                    sql.Placeholder(),
                )
            )
            params.append(value)

        return sql.SQL("WHERE {}").format(sql.SQL(" AND ").join(clauses)), params
