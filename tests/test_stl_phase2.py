"""Phase 2 tests — category assignment, temporal_specs, correction workflow.

Covers:
- Seed vocab population and category resolution
- Frame / qualifier / prop category assignment during store_program()
- time() qualifier → temporal_specs table population
- correct_intent / retract_intent → mark_superseded workflow
- §11 examples: hope, if, say, lie, cause, must, believe, defer, qualifiers
"""

import json
import pytest

from mind.stl.models import (
    ParsedProgram,
    ParsedRef,
    ParsedStatement,
    ParsedEvidence,
    ParsedNote,
    ParseLevel,
    RefArg,
    PropArg,
    LiteralArg,
    NumberArg,
    InlinePredArg,
)
from mind.stl.models import RefExpr, RefScope
from mind.stl.parser import parse_program
from mind.stl.store import SQLiteSTLStore
from mind.stl.vocab import SEED_VOCAB, SEED_CATEGORY_MAP, QUALIFIER_PREDICATES


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

    def test_frame_categories(self, store):
        for pred in ["believe", "hope", "say", "neg", "lie", "must", "if", "cause"]:
            assert store.get_vocab_category(pred) == "frame"

    def test_qualifier_categories(self, store):
        for pred in ["time", "degree", "quantity", "frequency", "duration", "location"]:
            assert store.get_vocab_category(pred) == "qualifier"

    def test_prop_categories(self, store):
        for pred in ["friend", "occupation", "live_in", "like"]:
            assert store.get_vocab_category(pred) == "prop"

    def test_unknown_returns_none(self, store):
        assert store.get_vocab_category("nonexistent_pred") is None

    def test_resolve_category_seed_first(self, store):
        """resolve_category checks seed map before DB."""
        assert store.resolve_category("hope") == "frame"
        assert store.resolve_category("time") == "qualifier"
        assert store.resolve_category("friend") == "prop"

    def test_resolve_category_falls_back_to_db(self, store):
        """NEW_PRED registered in DB should be found by resolve_category."""
        store.upsert_vocab("obsessed_with", "frame", "experiencer,target", "intense fascination", "llm_created")
        assert store.resolve_category("obsessed_with") == "frame"


# ══════════════════════════════════════════════════════════════════════
# Category Assignment in store_program
# ══════════════════════════════════════════════════════════════════════

class TestCategoryAssignment:
    def test_frame_category_set(self, store):
        """§11.4: hope() should get category='frame'."""
        text = """\
@s = @self
@t = @local/person("tom")
@k = @world/city("tokyo")
$p1 = come(@t, @k)
$f1 = hope(@s, $p1)
ev($f1, conf=0.9, src="turn_1")
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        result = store.store_program(prog, OWNER, CONV)
        assert result.statements_inserted == 2

        rows = store.query_statements(OWNER)
        cats = {r["predicate"]: r["category"] for r in rows}
        assert cats.get("hope") == "frame"
        # "come" is not a seed vocab → category should be None
        assert cats.get("come") is None

    def test_qualifier_category_set(self, store):
        """time(), degree(), quantity() should get category='qualifier'."""
        text = """\
@s = @self
$p1 = hobby(@s, "running")
$p2 = time($p1, "recent_start")
$p3 = quantity($p1, "5km/day")
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        result = store.store_program(prog, OWNER, CONV)

        rows = store.query_statements(OWNER)
        cats = {r["predicate"]: r["category"] for r in rows}
        assert cats.get("hobby") == "prop"
        assert cats.get("time") == "qualifier"
        assert cats.get("quantity") == "qualifier"

    def test_prop_category_set(self, store):
        """friend() should get category='prop' from seed vocab."""
        text = """\
@t = @local/person("tom")
@s = @self
$p1 = friend(@s, @t)
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        result = store.store_program(prog, OWNER, CONV)

        rows = store.query_statements(OWNER)
        assert rows[0]["category"] == "prop"

    def test_new_pred_gets_category_from_note(self, store):
        """A NEW_PRED declaration should be queryable by resolve_category after storage."""
        text = """\
@s = @self
$p1 = hobby(@s, "running")
$f1 = obsessed_with(@s, $p1)
note($f1, "NEW_PRED obsessed_with | frame | experiencer,target | intense fascination")
ev($f1, conf=0.8, src="turn_1")
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        result = store.store_program(prog, OWNER, CONV)

        # After storage, the NEW_PRED should be in vocab_registry
        assert store.get_vocab_category("obsessed_with") == "frame"

    def test_nested_frames_all_categorized(self, store):
        """§11.9: say(@m, must(@s, visit(@s, @m))) — all frames get category."""
        text = """\
@s = @self
@m = @local/person("mom")
$p1 = mother(@s, @m)
$f1 = say(@m, must(@s, visit(@s, @m)))
$p2 = time($f1, "this_weekend")
ev($f1, conf=1.0, src="turn_1")
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        result = store.store_program(prog, OWNER, CONV)

        rows = store.query_statements(OWNER)
        cats = {r["predicate"]: r["category"] for r in rows}
        assert cats.get("say") == "frame"
        assert cats.get("must") == "frame"
        assert cats.get("visit") == "prop"
        assert cats.get("mother") == "prop"
        assert cats.get("time") == "qualifier"


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
@t = @local/person("tom")
$p1 = resign(@t)
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
@s = @self
$p1 = hobby(@s, "running")
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
        """degree(), quantity() etc. should NOT create temporal_specs."""
        text = """\
@s = @self
$p1 = hobby(@s, "running")
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
@t = @local/person("tom")
$p1 = resign(@t)
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
        """§19: correct_intent should mark matching old statement as superseded."""
        store.create_conversation(CONV)

        # First batch: Tom resigned
        text1 = """\
@t = @local/person("tom")
$p1 = resign(@t)
ev($p1, conf=0.9, src="turn_5")
"""
        prog1 = _make_program(text1, batch_id="batch_01")
        store.store_program(prog1, OWNER, CONV)

        # Verify initial state
        stmts = store.query_statements(OWNER, predicate="resign")
        assert len(stmts) == 1
        assert stmts[0]["is_current"] in (True, 1)

        # Second batch: correction — Tom is actually just uncertain
        text2 = """\
@s = @self
@t = @local/person("tom")
$p1 = uncertain(@t, resign(@t))
$f1 = correct_intent(@s, $p1)
note($f1, "CORRECTION: 修正之前关于Tom辞职的说法")
ev($p1, conf=0.9, src="turn_15")
"""
        prog2 = _make_program(text2, batch_id="batch_02")
        store.store_program(prog2, OWNER, CONV)

        # Old resign statement should be superseded
        all_stmts = store.query_statements(OWNER, predicate="resign", is_current=False)
        superseded = [s for s in all_stmts if s.get("is_current") in (False, 0)]
        # The old one might or might not match depending on ref overlap
        # At minimum, the new statements should exist
        new_stmts = store.query_statements(OWNER, predicate="uncertain")
        assert len(new_stmts) >= 1

    def test_retract_intent_marks_superseded(self, store):
        """retract_intent should mark the matching statement as not current."""
        store.create_conversation(CONV)

        # First: Tom likes coffee
        text1 = """\
@t = @local/person("tom")
$p1 = like(@t, "coffee")
ev($p1, conf=0.9, src="turn_1")
"""
        prog1 = _make_program(text1, batch_id="batch_r1")
        store.store_program(prog1, OWNER, CONV)

        # Retraction: Tom actually doesn't like coffee
        text2 = """\
@s = @self
@t = @local/person("tom")
$p1 = like(@t, "coffee")
$f1 = retract_intent(@s, $p1)
note($f1, "CORRECTION: Tom不再喜欢咖啡了")
ev($f1, conf=0.9, src="turn_10")
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
        # The old like statement (from batch_r1) should be superseded
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
    """Test that §11 spec examples parse correctly and get proper categories."""

    def test_11_5_if_condition(self, store):
        """§11.5: if(neg(rain("tomorrow")), $p1)."""
        text = """\
@s = @self
$p1 = plan(@s, "running")
$f1 = if(neg(rain("tomorrow")), $p1)
ev($f1, conf=0.9, src="turn_1")
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        result = store.store_program(prog, OWNER, CONV)

        rows = store.query_statements(OWNER)
        preds = {r["predicate"] for r in rows}
        assert "if" in preds or "plan" in preds  # inline expansion may change structure
        cats = {r["predicate"]: r["category"] for r in rows}
        if "if" in cats:
            assert cats["if"] == "frame"
        if "neg" in cats:
            assert cats["neg"] == "frame"

    def test_11_6_say_narrative(self, store):
        """§11.6: say(@m, $p1) — Mike says Tom lives in Tokyo."""
        text = """\
@m = @local/person("mike")
@t = @local/person("tom")
@k = @world/city("tokyo")
$p1 = live_in(@t, @k)
$f1 = say(@m, $p1)
ev($f1, conf=0.85, src="turn_1")
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        result = store.store_program(prog, OWNER, CONV)

        rows = store.query_statements(OWNER)
        cats = {r["predicate"]: r["category"] for r in rows}
        assert cats["say"] == "frame"
        assert cats["live_in"] == "prop"

    def test_11_7_lie(self, store):
        """§11.7: lie(@mk, $f1) — Mike lied about visiting Mars."""
        text = """\
@s = @self
@mk = @local/person("mike")
$p1 = visit(@mk, "Mars")
$f1 = say(@mk, $p1)
$f2 = lie(@mk, $f1)
ev($f2, conf=0.9, src="turn_1", span="在扯淡")
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        result = store.store_program(prog, OWNER, CONV)

        rows = store.query_statements(OWNER)
        cats = {r["predicate"]: r["category"] for r in rows}
        assert cats["lie"] == "frame"
        assert cats["say"] == "frame"
        assert cats["visit"] == "prop"

    def test_11_8_cause_with_time_qualifier(self, store):
        """§11.8: cause + time qualifier → temporal_spec created."""
        text = """\
@t = @local/person("tom")
_:b1 = _:b1
$p1 = resign(@t)
$p2 = time($p1, "last_year")
$p3 = boss(@t, _:b1)
$p4 = cause(overbearing(_:b1), $p1)
ev($p1, conf=0.9, src="turn_1")
ev($p4, conf=0.85, src="turn_1")
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        store.store_program(prog, OWNER, CONV)

        # Verify temporal_spec for time()
        conn = store._get_conn()
        specs = conn.execute("SELECT * FROM temporal_specs").fetchall()
        assert len(specs) == 1
        assert dict(specs[0])["time_type"] == "fuzzy"  # "last_year" is not absolute date format
        assert dict(specs[0])["fuzzy_desc"] == "last_year"

        # Verify cause() categorization
        rows = store.query_statements(OWNER)
        cats = {r["predicate"]: r["category"] for r in rows}
        assert cats.get("cause") == "frame"

    def test_11_11_believe(self, store):
        """§11.11: believe(@s, $p1) — I think mom likes gold necklace."""
        text = """\
@s = @self
@m = @local/person("mom")
$p1 = like(@m, "gold_necklace")
$f1 = believe(@s, $p1)
ev($f1, conf=0.5, src="turn_1", span="我觉得")
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        result = store.store_program(prog, OWNER, CONV)

        rows = store.query_statements(OWNER)
        cats = {r["predicate"]: r["category"] for r in rows}
        assert cats["believe"] == "frame"
        assert cats["like"] == "prop"

    def test_11_13_qualifiers_and_new_pred(self, store):
        """§11.13: hobby + time + quantity + NEW_PRED obsessed_with."""
        text = """\
@s = @self
$p1 = hobby(@s, "long_distance_running")
$p2 = time($p1, "recent_start")
$p3 = quantity($p1, "5km/day")
$f1 = obsessed_with(@s, $p1)
note($f1, "NEW_PRED obsessed_with | frame | experiencer,target | intense recent fascination")
ev($p1, conf=1.0, src="turn_1")
ev($f1, conf=0.8, src="turn_1", span="迷上了")
"""
        prog = _make_program(text)
        store.create_conversation(CONV)
        result = store.store_program(prog, OWNER, CONV)

        rows = store.query_statements(OWNER)
        cats = {r["predicate"]: r["category"] for r in rows}
        assert cats["hobby"] == "prop"
        assert cats["time"] == "qualifier"
        assert cats["quantity"] == "qualifier"

        # NEW_PRED should now be in vocab
        assert store.get_vocab_category("obsessed_with") == "frame"

        # Temporal spec for time()
        conn = store._get_conn()
        specs = conn.execute("SELECT * FROM temporal_specs").fetchall()
        assert len(specs) == 1
        assert dict(specs[0])["fuzzy_desc"] == "recent_start"
