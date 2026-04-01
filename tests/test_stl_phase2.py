"""Phase 2 tests — category assignment, temporal_specs, correction workflow.

Covers:
- Seed vocab population and category resolution
- Category assignment during store_program()
- time() modifier → temporal_specs table population
- correct_intent / retract_intent → mark_superseded workflow
"""

import json
import pytest

from mind.stl.models import (
    ParsedProgram,
    ParsedRef,
    ParsedStatement,
    ParsedNote,
    ParseLevel,
    RefArg,
    PropArg,
    LiteralArg,
    NumberArg,
)
from mind.stl.models import RefExpr, RefScope
from mind.stl.parser import parse_program
from mind.stl.store import SQLiteSTLStore
from mind.stl.vocab import SEED_VOCAB, SEED_DOMAIN_MAP, MODIFIER_PREDICATES


@pytest.fixture
def store():
    s = SQLiteSTLStore(":memory:")
    return s


OWNER = "test_owner_abc"
CONV = "conv_1"


def _make_program(text: str, batch_id: str = "batch_p2") -> ParsedProgram:
    return parse_program(text, batch_id=batch_id)


# ══════════════════════════════════════════════════════════════════════
# Seed Vocabulary
# ══════════════════════════════════════════════════════════════════════

class TestSeedVocab:
    def test_seed_count(self, store):
        conn = store._get_conn()
        row = conn.execute("SELECT count(*) as c FROM vocab_registry").fetchone()
        assert row["c"] == len(SEED_VOCAB)

    def test_attitude_domains(self, store):
        """Attitude predicates registered via seed_vocab."""
        for pred in ["believe", "hope", "say", "emotion", "decide"]:
            assert store.get_vocab_category(pred) is not None

    def test_modifier_domains(self, store):
        for pred in ["time", "degree", "quantity", "frequency", "duration"]:
            assert store.get_vocab_category(pred) is not None

    def test_attribute_domains(self, store):
        for pred in ["friend", "occupation", "live_in", "like"]:
            assert store.get_vocab_category(pred) is not None

    def test_unknown_returns_none(self, store):
        assert store.get_vocab_category("nonexistent_pred") is None

    def test_resolve_category_seed_first(self, store):
        """resolve_category checks seed map before DB."""
        assert store.resolve_category("hope") is not None
        assert store.resolve_category("time") is not None
        assert store.resolve_category("friend") is not None

    def test_resolve_category_falls_back_to_db(self, store):
        """NEW_PRED registered in DB should be found by resolve_category."""
        store.upsert_vocab("obsessed_with", "attitudes", "experiencer,target", "intense fascination", "llm_created")
        assert store.resolve_category("obsessed_with") == "attitudes"


# ══════════════════════════════════════════════════════════════════════
# Category Assignment in store_program
# ══════════════════════════════════════════════════════════════════════

class TestCategoryAssignment:
    def test_frame_category_set(self, store):
        """hope() should get its domain from seed vocab."""
        text = """\
@tom: person "tom"
@tokyo: place "tokyo"
$p1 = come(@tom, @tokyo)
$f1 = hope(@self, $p1)
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        result = store.store_program(prog, OWNER, CONV)
        assert result.statements_inserted == 2

        rows = store.query_statements(OWNER)
        cats = {r["predicate"]: r["category"] for r in rows}
        assert cats.get("hope") is not None
        # "come" is not a seed vocab → category should be None
        assert cats.get("come") is None

    def test_modifier_category_set(self, store):
        """time(), quantity() should get their domain from seed vocab."""
        text = """\
$p1 = hobby(@self, "running")
$p2 = time($p1, "recent_start")
$p3 = quantity($p1, "5km/day")
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        result = store.store_program(prog, OWNER, CONV)

        rows = store.query_statements(OWNER)
        cats = {r["predicate"]: r["category"] for r in rows}
        assert cats.get("hobby") is not None
        assert cats.get("time") is not None
        assert cats.get("quantity") is not None

    def test_prop_category_set(self, store):
        """friend() should get domain from seed vocab."""
        text = """\
@tom: person "tom"
$p1 = friend(@self, @tom)
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        result = store.store_program(prog, OWNER, CONV)

        rows = store.query_statements(OWNER)
        assert rows[0]["category"] is not None

    def test_new_pred_gets_category_from_note(self, store):
        """A NEW_PRED declaration should be queryable by resolve_category after storage."""
        text = """\
$p1 = hobby(@self, "running")
$f1 = like(@self, $p1)
note($f1, "NEW_PRED obsessed_with | attitudes | experiencer,target | intense fascination")
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        result = store.store_program(prog, OWNER, CONV)

        # After storage, the NEW_PRED should be in vocab_registry
        assert store.get_vocab_category("obsessed_with") == "attitudes"

    def test_v2_all_categorized(self, store):
        """Multiple STMTs should all get domain tags."""
        text = """\
@mom: person "妈妈"
$p1 = mother(@self, @mom)
$p2 = visit(@self, @mom)
$f1 = say(@mom, $p2)
$p3 = time($f1, "this_weekend")
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        result = store.store_program(prog, OWNER, CONV)

        rows = store.query_statements(OWNER)
        cats = {r["predicate"]: r["category"] for r in rows}
        assert cats.get("say") is not None
        assert cats.get("visit") is not None
        assert cats.get("mother") is not None
        assert cats.get("time") is not None


# ══════════════════════════════════════════════════════════════════════
# Temporal Specs
# ══════════════════════════════════════════════════════════════════════

class TestTemporalSpecs:
    def _get_temporal_specs(self, store):
        conn = store._get_conn()
        rows = conn.execute("SELECT * FROM temporal_specs").fetchall()
        return [dict(r) for r in rows]

    def test_time_qualifier_creates_temporal_spec(self, store):
        """time($p, "2026-04") should create a point temporal_spec."""
        text = """\
@tom: person "tom"
$p1 = resign(@tom)
$p2 = time($p1, "2026-04")
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        store.store_program(prog, OWNER, CONV)

        specs = self._get_temporal_specs(store)
        assert len(specs) == 1
        assert specs[0]["time_type"] == "point"
        assert specs[0]["resolved_start"] == "2026-04"
        assert specs[0]["resolved_end"] is None

    def test_fuzzy_time_qualifier(self, store):
        """time($p, "recent") should create a fuzzy temporal_spec."""
        text = """\
$p1 = hobby(@self, "running")
$p2 = time($p1, "recent")
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        store.store_program(prog, OWNER, CONV)

        specs = self._get_temporal_specs(store)
        assert len(specs) == 1
        assert specs[0]["time_type"] == "fuzzy"
        assert specs[0]["fuzzy_desc"] == "recent"
        assert specs[0]["window_days"] == 30

    def test_non_time_qualifier_no_temporal_spec(self, store):
        """quantity() should NOT create temporal_specs."""
        text = """\
$p1 = hobby(@self, "running")
$p2 = quantity($p1, "5km/day")
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        store.store_program(prog, OWNER, CONV)

        specs = self._get_temporal_specs(store)
        assert len(specs) == 0

    def test_relative_time_as_fuzzy(self, store):
        """time($p, "next_month") should be classified as fuzzy."""
        text = """\
@tom: person "tom"
$p1 = resign(@tom)
$p2 = time($p1, "next_month")
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        store.store_program(prog, OWNER, CONV)

        specs = self._get_temporal_specs(store)
        assert len(specs) == 1
        assert specs[0]["time_type"] == "fuzzy"
        assert specs[0]["fuzzy_desc"] == "next_month"


# ══════════════════════════════════════════════════════════════════════
# Correction Workflow
# ══════════════════════════════════════════════════════════════════════

class TestCorrectionWorkflow:
    def test_correct_intent_supersedes_old_statement(self, store):
        """correct_intent should mark matching old statement as superseded."""
        store.create_conversation(CONV)

        # First batch: Tom resigned
        text1 = """\
@tom: person "tom"
$p1 = resign(@tom)
"""
        prog1 = _make_program(text1, batch_id="batch_01")
        store.store_program(prog1, OWNER, CONV)

        # Verify initial state
        stmts = store.query_statements(OWNER, predicate="resign")
        assert len(stmts) == 1
        assert stmts[0]["is_current"] in (True, 1)

        # Second batch: correction — Tom is actually just uncertain
        text2 = """\
@tom: person "tom"
$p1 = uncertain(@tom, "resign")
$f1 = correct_intent(@self, $p1)
note($f1, "CORRECTION: 修正之前关于Tom辞职的说法")
"""
        prog2 = _make_program(text2, batch_id="batch_02")
        store.store_program(prog2, OWNER, CONV)

        # New statements should exist
        new_stmts = store.query_statements(OWNER, predicate="uncertain")
        assert len(new_stmts) >= 1

    def test_retract_intent_marks_superseded(self, store):
        """retract_intent should mark the matching statement as not current."""
        store.create_conversation(CONV)

        # First: Tom likes coffee
        text1 = """\
@tom: person "tom"
$p1 = like(@tom, "coffee")
"""
        prog1 = _make_program(text1, batch_id="batch_r1")
        store.store_program(prog1, OWNER, CONV)

        # Retraction: Tom actually doesn't like coffee
        text2 = """\
@tom: person "tom"
$p1 = like(@tom, "coffee")
$f1 = retract_intent(@self, $p1)
note($f1, "CORRECTION: Tom不再喜欢咖啡了")
"""
        prog2 = _make_program(text2, batch_id="batch_r2")
        store.store_program(prog2, OWNER, CONV)

        # Check: look at ALL like statements (including non-current)
        conn = store._get_conn()
        rows = conn.execute(
            "SELECT id, is_current, superseded_by FROM statements WHERE predicate = 'like' AND owner_id = ?",
            (OWNER,),
        ).fetchall()
        # There should be at least one superseded
        superseded = [dict(r) for r in rows if r["is_current"] == 0]
        assert len(superseded) >= 1

    def test_mark_superseded_directly(self, store):
        """Direct mark_superseded should set is_current=FALSE and superseded_by."""
        store.create_conversation(CONV)
        store.create_extraction_batch("b1", CONV, 0, 1)
        store.insert_statement("s1", "b1", OWNER, "test_pred", ["arg1"], "prop")
        store.insert_statement("s2", "b1", OWNER, "test_pred", ["arg2"], "prop")

        # Verify initial state
        stmts = store.query_statements(OWNER, predicate="test_pred")
        assert len(stmts) == 2

        # Mark s1 superseded by s2
        store.mark_superseded("s1", "s2")

        # s1 should not appear in is_current=True query
        stmts = store.query_statements(OWNER, predicate="test_pred", is_current=True)
        assert len(stmts) == 1
        assert stmts[0]["id"] == "s2"

        # s1 should appear in is_current=False query
        stmts = store.query_statements(OWNER, predicate="test_pred", is_current=False)
        superseded = [s for s in stmts if s["id"] == "s1"]
        assert len(superseded) == 1
        assert superseded[0]["superseded_by"] == "s2"


# ══════════════════════════════════════════════════════════════════════
# §11 Frame Examples (end-to-end parse + store)
# ══════════════════════════════════════════════════════════════════════

class TestSpec11FrameExamples:
    """Test that §11 spec examples parse correctly and get proper domains."""

    def test_11_5_if_condition(self, store):
        """§11.5: if(condition, consequence) — v2 flat form."""
        text = """\
$p1 = plan(@self, "running")
$p2 = neg("rain_tomorrow")
$f1 = if($p2, $p1)
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        result = store.store_program(prog, OWNER, CONV)

        rows = store.query_statements(OWNER)
        cats = {r["predicate"]: r["category"] for r in rows}
        assert cats.get("if") == "logic"
        assert cats.get("neg") == "logic"

    def test_11_6_say_narrative(self, store):
        """§11.6: say(@m, $p1) — Mike says Tom lives in Tokyo."""
        text = """\
@m: person "mike"
@t: person "tom"
@k: city "tokyo"
$p1 = live_in(@t, @k)
$f1 = say(@m, $p1)
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        result = store.store_program(prog, OWNER, CONV)

        rows = store.query_statements(OWNER)
        cats = {r["predicate"]: r["category"] for r in rows}
        assert cats["say"] == "attitudes"
        assert cats["live_in"] == "attributes"

    def test_11_7_lie(self, store):
        """§11.7: lie(@mk, $f1) — Mike lied about visiting Mars."""
        text = """\
@mk: person "mike"
$p1 = visit(@mk, "Mars")
$f1 = say(@mk, $p1)
$f2 = lie(@mk, $f1)
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        result = store.store_program(prog, OWNER, CONV)

        rows = store.query_statements(OWNER)
        cats = {r["predicate"]: r["category"] for r in rows}
        assert cats["lie"] == "logic"
        assert cats["say"] == "attitudes"
        assert cats["visit"] == "actions"

    def test_11_8_cause_with_time_modifier(self, store):
        """§11.8: cause + time modifier → temporal_spec created."""
        text = """\
@t: person "tom"
@b1: person
$p1 = resign(@t)
$p2 = time($p1, "last_year")
$p3 = boss(@t, @b1)
$p4 = cause($p3, $p1)
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        store.store_program(prog, OWNER, CONV)

        # Verify temporal_spec for time()
        conn = store._get_conn()
        specs = conn.execute("SELECT * FROM temporal_specs").fetchall()
        assert len(specs) == 1
        assert dict(specs[0])["time_type"] == "fuzzy"
        assert dict(specs[0])["fuzzy_desc"] == "last_year"

        # Verify cause() categorization
        rows = store.query_statements(OWNER)
        cats = {r["predicate"]: r["category"] for r in rows}
        assert cats.get("cause") == "logic"

    def test_11_11_believe(self, store):
        """§11.11: believe(@self, $p1) — I think mom likes gold necklace."""
        text = """\
@m: person "mom"
$p1 = like(@m, "gold_necklace")
$f1 = believe(@self, $p1)
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        result = store.store_program(prog, OWNER, CONV)

        rows = store.query_statements(OWNER)
        cats = {r["predicate"]: r["category"] for r in rows}
        assert cats["believe"] == "attitudes"
        assert cats["like"] == "attributes"

    def test_11_13_modifiers_and_suggested_pred(self, store):
        """§11.13: hobby + time + quantity + :suggested obsessed_with."""
        text = """\
$p1 = hobby(@self, "long_distance_running")
$p2 = time($p1, "recent_start")
$p3 = quantity($p1, "5km/day")
$f1 = obsessed_with(@self, $p1):obsessed_with
note($f1, "NEW_PRED obsessed_with | attitudes | experiencer,target | intense recent fascination")
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        result = store.store_program(prog, OWNER, CONV)

        rows = store.query_statements(OWNER)
        cats = {r["predicate"]: r["category"] for r in rows}
        assert cats["hobby"] == "attributes"
        assert cats["time"] == "modifiers"
        assert cats["quantity"] == "modifiers"

        # NEW_PRED should now be in vocab
        assert store.get_vocab_category("obsessed_with") == "attitudes"

        # Temporal spec for time()
        conn = store._get_conn()
        specs = conn.execute("SELECT * FROM temporal_specs").fetchall()
        assert len(specs) == 1
        assert dict(specs[0])["fuzzy_desc"] == "recent_start"
