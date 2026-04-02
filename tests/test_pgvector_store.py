"""Unit tests for pgvector helper behavior that does not require a live database."""

from types import SimpleNamespace

from psycopg import sql

from mind.vector_stores.pgvector import PgVectorStore


class TestPgVectorStoreHelpers:
    """Exercise pure helper logic for the pgvector backend."""

    def test_payload_to_row_keeps_known_columns(self):
        payload = {
            "user_id": "alice",
            "owner_id": "owner-1",
            "subject_ref": "self",
            "fact_family": "preference",
            "relation_type": "self",
            "field_key": "preference:general",
            "field_value_json": {"value": "black coffee"},
            "canonical_text": "[self] preference:general=black coffee",
            "raw_text": "I love black coffee",
            "content": "User likes black coffee",
            "hash": "abc",
            "metadata": {"source": "test"},
            "created_at": "2026-03-30T00:00:00+00:00",
            "updated_at": "2026-03-30T00:00:00+00:00",
            "confidence": 0.9,
            "status": "active",
            "source_context": "conversation",
            "source_session_id": "sess-1",
            "version_of": None,
            "importance": 0.5,
            "type": "preference",
            "ignored": "value",
        }

        row = PgVectorStore._payload_to_row(payload)

        assert row["user_id"] == "alice"
        assert row["owner_id"] == "owner-1"
        assert row["subject_ref"] == "self"
        assert row["field_value_json"] == {"value": "black coffee"}
        assert row["content"] == "User likes black coffee"
        assert row["metadata"] == {"source": "test"}
        assert "ignored" not in row

    def test_payload_to_row_partial_only_includes_present_fields(self):
        row = PgVectorStore._payload_to_row(
            {"status": "deleted", "updated_at": "2026-03-30T00:00:00+00:00"},
            partial=True,
        )

        assert row == {
            "updated_at": "2026-03-30T00:00:00+00:00",
            "status": "deleted",
        }

    def test_row_to_payload_restores_metadata_default(self):
        payload = PgVectorStore._row_to_payload({
            "user_id": "alice",
            "owner_id": "owner-1",
            "subject_ref": "self",
            "fact_family": "attribute",
            "relation_type": "self",
            "field_key": "name",
            "field_value_json": None,
            "canonical_text": None,
            "raw_text": None,
            "content": "User likes coffee",
            "hash": "abc",
            "metadata": None,
            "created_at": None,
            "updated_at": None,
            "confidence": None,
            "status": "active",
            "source_context": None,
            "source_session_id": None,
            "version_of": None,
            "importance": None,
            "type": None,
        })

        assert payload["metadata"] == {}
        assert payload["field_value_json"] == {}
        assert payload["status"] == "active"

    def test_build_filter_returns_sql_and_params(self):
        clause, params = PgVectorStore._build_filter(
            {"user_id": "alice", "status": "active"},
            sql,
        )

        assert params == ["alice", "active"]
        assert clause.as_string(None).startswith("WHERE ")

    def test_build_filter_rejects_unknown_keys(self):
        try:
            PgVectorStore._build_filter({"unknown": "value"}, sql)
        except ValueError as exc:
            assert "Unsupported pgvector filter key" in str(exc)
        else:
            raise AssertionError("Expected ValueError for unsupported filter key")

    def test_create_collection_formats_jsonb_default_without_placeholder_error(
        self,
        monkeypatch,
    ):
        class FakeCursor:
            def __init__(self):
                self.executed = []

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, query, params=None):
                self.executed.append((query, params))

        class FakeConnection:
            def __init__(self):
                self.cursor_obj = FakeCursor()

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def cursor(self):
                return self.cursor_obj

        store = PgVectorStore(
            SimpleNamespace(
                dsn="postgresql://postgres:postgres@localhost:5432/mind",
                collection_name="mind_memories",
            )
        )
        fake_conn = FakeConnection()

        monkeypatch.setattr(store, "_connect", lambda register_types=False: fake_conn)
        monkeypatch.setattr(
            store,
            "_load_modules",
            lambda: (
                object(),
                object(),
                lambda _conn: None,
                sql,
                object(),
                object(),
            ),
        )

        store.create_collection(128)

        rendered = "\n".join(
            query.as_string(None) if hasattr(query, "as_string") else str(query)
            for query, _params in fake_conn.cursor_obj.executed
        )
        assert "DEFAULT '{}'::jsonb" in rendered
