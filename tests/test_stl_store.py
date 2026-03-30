"""Tests for the STL relational store — SQLite backend."""

import json
import pytest

from mind.stl.store import SQLiteSTLStore, STLStoreFactory
from mind.stl.models import (
    ParsedProgram,
    ParsedRef,
    ParsedStatement,
    ParsedEvidence,
    ParsedNote,
    FailedLine,
    RefExpr,
    RefScope,
    RefArg,
    LiteralArg,
    ParseLevel,
)


@pytest.fixture
def store(tmp_path):
    db = SQLiteSTLStore(db_path=str(tmp_path / "test_stl.db"))
    yield db
    db.close()


@pytest.fixture
def memory_store():
    """In-memory store for fast tests."""
    db = SQLiteSTLStore(db_path=":memory:")
    yield db
    db.close()


# ══════════════════════════════════════════════════════════════════════
# Schema creation
# ══════════════════════════════════════════════════════════════════════

class TestSchema:
    def test_tables_created(self, memory_store):
        conn = memory_store._get_conn()
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t["name"] for t in tables}
        expected = {
            "conversations", "turns", "extraction_batches",
            "refs", "statements", "stmt_refs", "evidence",
            "notes", "vocab_registry", "coreference",
            "coref_pending", "temporal_specs",
        }
        assert expected.issubset(table_names)


# ══════════════════════════════════════════════════════════════════════
# CRUD operations
# ══════════════════════════════════════════════════════════════════════

class TestCRUD:
    def test_upsert_ref(self, memory_store):
        ref_id = memory_store.upsert_ref(
            ref_id="r1", scope="local", ref_type="person",
            key="tom", aliases=["tommy"], owner_id="owner1",
        )
        assert ref_id == "r1"

    def test_ref_dedup_by_key(self, memory_store):
        memory_store.upsert_ref(
            ref_id="r1", scope="local", ref_type="person",
            key="tom", aliases=["tommy"], owner_id="owner1",
        )
        ref_id2 = memory_store.upsert_ref(
            ref_id="r2", scope="local", ref_type="person",
            key="tom", aliases=["t"], owner_id="owner1",
        )
        # Should return existing r1, not create r2
        assert ref_id2 == "r1"

    def test_ref_alias_merge(self, memory_store):
        memory_store.upsert_ref(
            ref_id="r1", scope="local", ref_type="person",
            key="tom", aliases=["tommy"], owner_id="owner1",
        )
        memory_store.upsert_ref(
            ref_id="r2", scope="local", ref_type="person",
            key="tom", aliases=["t"], owner_id="owner1",
        )
        conn = memory_store._get_conn()
        row = conn.execute("SELECT aliases FROM refs WHERE id = ?", ("r1",)).fetchone()
        aliases = json.loads(row["aliases"])
        assert "tommy" in aliases
        assert "t" in aliases

    def test_get_ref_by_key(self, memory_store):
        memory_store.upsert_ref(
            ref_id="r1", scope="self", ref_type=None,
            key=None, aliases=[], owner_id="owner1",
        )
        assert memory_store.get_ref_by_key("owner1", "self", None, None) == "r1"
        assert memory_store.get_ref_by_key("owner2", "self", None, None) is None

    def test_create_conversation(self, memory_store):
        memory_store.create_conversation("conv1")
        conn = memory_store._get_conn()
        row = conn.execute("SELECT * FROM conversations WHERE id = 'conv1'").fetchone()
        assert row is not None

    def test_create_turn(self, memory_store):
        memory_store.create_conversation("conv1")
        turn_id = memory_store.create_turn("conv1", 0, "user", "Hello")
        assert turn_id is not None

    def test_insert_statement(self, memory_store):
        memory_store.create_conversation("conv1")
        memory_store.create_extraction_batch("b1", "conv1", 0, 1)
        memory_store.insert_statement(
            stmt_id="s1", batch_id="b1", owner_id="owner1",
            predicate="friend", args_json=["@r1", "@r2"],
        )
        rows = memory_store.query_statements("owner1")
        assert len(rows) == 1
        assert rows[0]["predicate"] == "friend"

    def test_insert_evidence(self, memory_store):
        memory_store.insert_evidence(
            target_id="s1", conf=0.9, src="turn_1", span="我朋友",
        )
        conn = memory_store._get_conn()
        row = conn.execute("SELECT * FROM evidence WHERE target_id = 's1'").fetchone()
        assert row["conf"] == 0.9

    def test_insert_note(self, memory_store):
        memory_store.insert_note("s1", "Some explanation")
        conn = memory_store._get_conn()
        row = conn.execute("SELECT * FROM notes WHERE target_id = 's1'").fetchone()
        assert "explanation" in row["content"]

    def test_upsert_vocab(self, memory_store):
        memory_store.upsert_vocab(
            "obsessed_with", "frame", "experiencer,target",
            "intense recent fascination", "llm_created",
        )
        conn = memory_store._get_conn()
        row = conn.execute("SELECT * FROM vocab_registry WHERE word = 'obsessed_with'").fetchone()
        assert row["category"] == "frame"

    def test_vocab_usage_count(self, memory_store):
        memory_store.upsert_vocab("test_word", "prop", None, "test def", "seed")
        memory_store.upsert_vocab("test_word", "prop", None, "test def", "llm_created")
        conn = memory_store._get_conn()
        row = conn.execute("SELECT usage_count FROM vocab_registry WHERE word = 'test_word'").fetchone()
        assert row["usage_count"] == 1

    def test_query_statements_by_predicate(self, memory_store):
        memory_store.create_conversation("conv1")
        memory_store.create_extraction_batch("b1", "conv1", 0, 1)
        memory_store.insert_statement("s1", "b1", "o1", "friend", ["@r1", "@r2"])
        memory_store.insert_statement("s2", "b1", "o1", "name", ["@r1", '"Alice"'])
        rows = memory_store.query_statements("o1", predicate="friend")
        assert len(rows) == 1
        assert rows[0]["id"] == "s1"


# ══════════════════════════════════════════════════════════════════════
# store_program (high-level)
# ══════════════════════════════════════════════════════════════════════

class TestStoreProgram:
    def _make_program(self):
        """Build a minimal ParsedProgram for testing."""
        return ParsedProgram(
            batch_id="batch_1",
            refs=[
                ParsedRef(
                    local_id="s",
                    expr=RefExpr(scope=RefScope.SELF),
                    parse_level=ParseLevel.STRICT,
                ),
                ParsedRef(
                    local_id="t",
                    expr=RefExpr(scope=RefScope.LOCAL, ref_type="person", key="tom"),
                    parse_level=ParseLevel.STRICT,
                ),
            ],
            statements=[
                ParsedStatement(
                    local_id="p1",
                    predicate="friend",
                    args=[RefArg(ref_id="s"), RefArg(ref_id="t")],
                    parse_level=ParseLevel.STRICT,
                ),
                ParsedStatement(
                    local_id="p2",
                    predicate="occupation",
                    args=[RefArg(ref_id="t"), LiteralArg(value="football_player")],
                    parse_level=ParseLevel.STRICT,
                ),
            ],
            evidence=[
                ParsedEvidence(
                    target_local_id="p1", conf=1.0, src="turn_1",
                ),
                ParsedEvidence(
                    target_local_id="p2", conf=0.9, src="turn_1",
                ),
            ],
            notes=[],
            failed=[],
        )

    def test_store_program_basic(self, memory_store):
        prog = self._make_program()
        memory_store.create_conversation("conv1")
        result = memory_store.store_program(prog, owner_id="owner1", conv_id="conv1")
        assert result.refs_upserted >= 1
        assert result.statements_inserted == 2
        assert result.evidence_inserted == 2
        assert len(result.errors) == 0

    def test_self_ref_auto_created(self, memory_store):
        prog = self._make_program()
        memory_store.create_conversation("conv1")
        memory_store.store_program(prog, owner_id="owner1", conv_id="conv1")
        self_ref = memory_store.get_ref_by_key("owner1", "self", None, None)
        assert self_ref is not None

    def test_statements_queryable(self, memory_store):
        prog = self._make_program()
        memory_store.create_conversation("conv1")
        memory_store.store_program(prog, owner_id="owner1", conv_id="conv1")
        rows = memory_store.query_statements("owner1")
        assert len(rows) == 2

    def test_new_pred_vocab_registration(self, memory_store):
        prog = ParsedProgram(
            batch_id="batch_2",
            refs=[
                ParsedRef(
                    local_id="s",
                    expr=RefExpr(scope=RefScope.SELF),
                    parse_level=ParseLevel.STRICT,
                ),
            ],
            statements=[
                ParsedStatement(
                    local_id="f1",
                    predicate="obsessed_with",
                    args=[RefArg(ref_id="s"), LiteralArg(value="long_distance_running")],
                    parse_level=ParseLevel.STRICT,
                ),
            ],
            evidence=[],
            notes=[
                ParsedNote(
                    target_local_id="f1",
                    text="NEW_PRED obsessed_with | frame | experiencer,target | intense recent fascination",
                ),
            ],
            failed=[],
        )
        memory_store.create_conversation("conv2")
        result = memory_store.store_program(prog, owner_id="owner1", conv_id="conv2")
        assert result.vocab_registered == 1
        conn = memory_store._get_conn()
        row = conn.execute("SELECT * FROM vocab_registry WHERE word = 'obsessed_with'").fetchone()
        assert row is not None
        assert row["category"] == "frame"


# ══════════════════════════════════════════════════════════════════════
# Factory
# ══════════════════════════════════════════════════════════════════════

class TestSTLStoreFactory:
    def test_sqlite_factory(self):
        class FakeConfig:
            provider = "sqlite"
            db_path = ":memory:"
        store = STLStoreFactory.create(FakeConfig())
        assert isinstance(store, SQLiteSTLStore)
        store.close()

    def test_unknown_provider_raises(self):
        class FakeConfig:
            provider = "mongodb"
        with pytest.raises(ValueError, match="Unknown STL store provider"):
            STLStoreFactory.create(FakeConfig())
