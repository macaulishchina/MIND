"""Tests for STL Phase 3 features.

Covers:
- Focus Stack scoring & update (§17)
- Temporal resolution with anchor_date (§18)
- Vocabulary collision detection (§9)
- Store coreference / coref_pending methods
"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from mind.stl.focus import (
    AMBIGUITY_MARGIN,
    AUTO_ACCEPT_THRESHOLD,
    FocusEntry,
    FocusStack,
    GRAMMAR_OBJECT,
    GRAMMAR_SUBJECT,
    LONG_GAP_PENALTY,
    LONG_GAP_TURNS,
    RECENCY_DECAY,
)
from mind.stl.models import (
    ParsedProgram,
    ParsedRef,
    ParsedStatement,
    PropArg,
    RefArg,
    RefExpr,
    RefScope,
    LiteralArg,
)
from mind.stl.store import (
    SQLiteSTLStore,
    _classify_time_value,
    _cosine_sim,
    _resolve_relative_time,
)


# ══════════════════════════════════════════════════════════════════════
# Focus Stack scoring tests (§17)
# ══════════════════════════════════════════════════════════════════════


class TestFocusStack:
    """FocusStack scoring, update, and top-k."""

    def test_empty_stack(self):
        fs = FocusStack()
        assert fs.entries == []
        assert fs.top_k_for_prompt() == []

    def test_bootstrap_from_refs(self):
        fs = FocusStack()
        refs = [
            {"id": "ref1", "scope": "named", "ref_type": "person", "key": "tom", "aliases": []},
            {"id": "ref2", "scope": "named", "ref_type": "city", "key": "tokyo", "aliases": []},
        ]
        fs.bootstrap_from_refs(refs, current_turn=5)
        assert len(fs.entries) == 2
        # Both should have scores > 0
        for entry in fs.entries:
            assert entry.score >= 0

    def test_bootstrap_skips_self_scope(self):
        fs = FocusStack()
        refs = [
            {"id": "self_001", "scope": "self", "ref_type": None, "key": None, "aliases": []},
            {"id": "ref1", "scope": "named", "ref_type": "person", "key": "tom", "aliases": []},
        ]
        fs.bootstrap_from_refs(refs, current_turn=0)
        assert len(fs.entries) == 1
        assert fs.entries[0].ref_id == "ref1"

    def test_bootstrap_deduplicates(self):
        fs = FocusStack()
        refs = [
            {"id": "ref1", "scope": "named", "ref_type": "person", "key": "tom", "aliases": []},
        ]
        fs.bootstrap_from_refs(refs, current_turn=0)
        fs.bootstrap_from_refs(refs, current_turn=1)  # same ref again
        assert len(fs.entries) == 1

    def test_recency_decay(self):
        """Score should decay with gap from last mention."""
        fs = FocusStack()
        refs = [
            {"id": "ref1", "scope": "named", "ref_type": "person", "key": "tom", "aliases": []},
        ]
        fs.bootstrap_from_refs(refs, current_turn=0)
        score_at_0 = fs.entries[0].score

        fs._recompute_scores(current_turn=5)
        score_at_5 = fs.entries[0].score

        assert score_at_5 < score_at_0  # score decayed

    def test_update_from_program(self):
        """update() should add new entities and refresh scores."""
        fs = FocusStack()
        program = ParsedProgram(
            batch_id="b1",
            refs=[
                ParsedRef(local_id="t", expr=RefExpr(scope=RefScope.NAMED, ref_type="person", key="tom")),
            ],
            statements=[
                ParsedStatement(
                    local_id="p1",
                    predicate="friend",
                    args=[RefArg(ref_id="s"), RefArg(ref_id="t")],
                ),
            ],
        )
        ref_map = {"t": "global_tom"}
        fs.update(program, current_turn=3, ref_map=ref_map)

        assert len(fs.entries) == 1
        entry = fs.entries[0]
        assert entry.ref_id == "global_tom"
        assert entry.last_mentioned_turn == 3
        assert entry.mention_count >= 1

    def test_update_skips_self(self):
        """update() should not track @self refs."""
        fs = FocusStack()
        program = ParsedProgram(
            batch_id="b1",
            refs=[
                ParsedRef(local_id="s", expr=RefExpr(scope=RefScope.SELF)),
            ],
            statements=[],
        )
        fs.update(program, current_turn=1)
        assert len(fs.entries) == 0

    def test_top_k_ordering(self):
        """Entities should be ranked by score descending."""
        fs = FocusStack(top_k=2)
        # Manually add entries
        fs._entries["a"] = FocusEntry(ref_id="a", ref_expr="@a", score=0.8, last_mentioned_turn=1)
        fs._entries["b"] = FocusEntry(ref_id="b", ref_expr="@b", score=0.5, last_mentioned_turn=1)
        fs._entries["c"] = FocusEntry(ref_id="c", ref_expr="@c", score=0.9, last_mentioned_turn=1)

        top = fs.top_k_for_prompt()
        assert len(top) == 2
        assert top[0]["ref_expr"] == "@c"
        assert top[1]["ref_expr"] == "@a"

    def test_top_k_excludes_zero_score(self):
        """Zero-score entries should not appear in top-k."""
        fs = FocusStack()
        fs._entries["a"] = FocusEntry(ref_id="a", ref_expr="@a", score=0.0)
        assert fs.top_k_for_prompt() == []

    def test_resolve_ambiguous_clear_winner(self):
        """resolve_ambiguous should return top1 when margin is wide enough."""
        fs = FocusStack()
        fs._entries["a"] = FocusEntry(ref_id="a", ref_expr="@a", score=0.8)
        fs._entries["b"] = FocusEntry(ref_id="b", ref_expr="@b", score=0.3)

        result = fs.resolve_ambiguous("a", "b")
        assert result == "a"

    def test_resolve_ambiguous_too_close(self):
        """resolve_ambiguous should return None when scores too close."""
        fs = FocusStack()
        fs._entries["a"] = FocusEntry(ref_id="a", ref_expr="@a", score=0.55)
        fs._entries["b"] = FocusEntry(ref_id="b", ref_expr="@b", score=0.50)

        result = fs.resolve_ambiguous("a", "b")
        assert result is None  # ambiguous

    def test_long_gap_penalty(self):
        """Entities not mentioned for >8 turns should get penalized."""
        fs = FocusStack()
        fs._entries["a"] = FocusEntry(
            ref_id="a", ref_expr="@a",
            last_mentioned_turn=0, mention_count=5,
        )
        # Turn 1 — small gap
        fs._recompute_scores(current_turn=1)
        score_small_gap = fs.entries[0].score

        # Turn 10 — big gap (>8)
        fs._recompute_scores(current_turn=10)
        score_big_gap = fs.entries[0].score

        # The big gap has extra penalty applied
        assert score_big_gap < score_small_gap

    def test_grammar_role_subject_vs_object(self):
        """Subject position should produce higher grammar score."""
        # Create program where entity is in subject position (pos=0)
        program_subj = ParsedProgram(
            batch_id="b1",
            refs=[
                ParsedRef(local_id="t", expr=RefExpr(scope=RefScope.NAMED, ref_type="person", key="tom")),
            ],
            statements=[
                ParsedStatement(
                    local_id="p1",
                    predicate="like",
                    args=[RefArg(ref_id="t"), LiteralArg(value="coffee")],
                ),
            ],
        )
        fs1 = FocusStack()
        fs1.update(program_subj, current_turn=1, ref_map={"t": "tom1"})
        score_subj = fs1.entries[0].score

        # Create program where entity is in object position (pos=1)
        program_obj = ParsedProgram(
            batch_id="b2",
            refs=[
                ParsedRef(local_id="t", expr=RefExpr(scope=RefScope.NAMED, ref_type="person", key="tom")),
            ],
            statements=[
                ParsedStatement(
                    local_id="p1",
                    predicate="like",
                    args=[RefArg(ref_id="s"), RefArg(ref_id="t")],
                ),
            ],
        )
        fs2 = FocusStack()
        fs2.update(program_obj, current_turn=1, ref_map={"t": "tom2"})
        score_obj = fs2.entries[0].score

        assert score_subj > score_obj


# ══════════════════════════════════════════════════════════════════════
# Time resolution tests (§18)
# ══════════════════════════════════════════════════════════════════════


class TestTimeResolution:
    """Temporal resolution with anchor_date."""

    ANCHOR = date(2026, 3, 30)

    def test_absolute_date_unchanged(self):
        """Absolute dates should remain as-is regardless of anchor."""
        tt, rs, re, fd, wd = _classify_time_value("2026-04", anchor_date=self.ANCHOR)
        assert tt == "point"
        assert rs == "2026-04"

    def test_next_month(self):
        tt, rs, re, fd, wd = _classify_time_value("next_month", anchor_date=self.ANCHOR)
        assert tt == "point"
        assert rs == "2026-04"
        assert fd == "next_month"

    def test_last_year(self):
        tt, rs, re, fd, wd = _classify_time_value("last_year", anchor_date=self.ANCHOR)
        assert tt == "point"
        assert rs == "2025"

    def test_this_year(self):
        tt, rs, re, fd, wd = _classify_time_value("this_year", anchor_date=self.ANCHOR)
        assert tt == "point"
        assert rs == "2026"

    def test_today(self):
        tt, rs, re, fd, wd = _classify_time_value("today", anchor_date=self.ANCHOR)
        assert tt == "point"
        assert rs == "2026-03-30"

    def test_yesterday(self):
        tt, rs, re, fd, wd = _classify_time_value("yesterday", anchor_date=self.ANCHOR)
        assert tt == "point"
        assert rs == "2026-03-29"

    def test_tomorrow(self):
        tt, rs, re, fd, wd = _classify_time_value("tomorrow", anchor_date=self.ANCHOR)
        assert tt == "point"
        assert rs == "2026-03-31"

    def test_this_weekend(self):
        """2026-03-30 is Monday, so this weekend = April 4-5."""
        tt, rs, re, fd, wd = _classify_time_value("this_weekend", anchor_date=self.ANCHOR)
        assert tt == "interval"
        assert rs == "2026-04-04"
        assert re == "2026-04-05"

    def test_next_week(self):
        """Next Monday from 2026-03-30 (Monday) = 2026-04-06."""
        tt, rs, re, fd, wd = _classify_time_value("next_week", anchor_date=self.ANCHOR)
        assert tt == "point"
        assert rs == "2026-04-06"

    def test_last_month(self):
        tt, rs, re, fd, wd = _classify_time_value("last_month", anchor_date=self.ANCHOR)
        assert tt == "point"
        assert rs == "2026-02"

    def test_fuzzy_without_anchor(self):
        """Without anchor, relative expressions become fuzzy."""
        tt, rs, re, fd, wd = _classify_time_value("next_month")
        assert tt == "fuzzy"
        assert fd == "next_month"

    def test_fuzzy_recent(self):
        tt, rs, re, fd, wd = _classify_time_value("recent", anchor_date=self.ANCHOR)
        assert tt == "fuzzy"
        assert fd == "recent"
        assert wd == 30

    def test_interval_explicit(self):
        tt, rs, re, fd, wd = _classify_time_value("2026-04", "2026-06")
        assert tt == "interval"
        assert rs == "2026-04"
        assert re == "2026-06"

    def test_chinese_relative(self):
        """Chinese relative time expressions should resolve."""
        tt, rs, re, fd, wd = _classify_time_value("明天", anchor_date=self.ANCHOR)
        assert tt == "point"
        assert rs == "2026-03-31"

    def test_chinese_last_year(self):
        tt, rs, re, fd, wd = _classify_time_value("去年", anchor_date=self.ANCHOR)
        assert tt == "point"
        assert rs == "2025"


class TestResolveRelativeTime:
    """Direct tests for _resolve_relative_time helper."""

    ANCHOR = date(2026, 3, 30)

    def test_unknown_expression(self):
        start, end = _resolve_relative_time("unknown_expr", self.ANCHOR)
        assert start is None
        assert end is None

    def test_day_before_yesterday(self):
        start, end = _resolve_relative_time("day_before_yesterday", self.ANCHOR)
        assert start == "2026-03-28"

    def test_day_after_tomorrow(self):
        start, end = _resolve_relative_time("day_after_tomorrow", self.ANCHOR)
        assert start == "2026-04-01"

    def test_next_year(self):
        start, end = _resolve_relative_time("next_year", self.ANCHOR)
        assert start == "2027"


# ══════════════════════════════════════════════════════════════════════
# Cosine similarity helper
# ══════════════════════════════════════════════════════════════════════


class TestCosineSim:
    def test_identical_vectors(self):
        assert _cosine_sim([1, 0, 0], [1, 0, 0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert _cosine_sim([1, 0], [0, 1]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert _cosine_sim([1, 0], [-1, 0]) == pytest.approx(-1.0)

    def test_zero_vector(self):
        assert _cosine_sim([0, 0], [1, 0]) == 0.0


# ══════════════════════════════════════════════════════════════════════
# Vocabulary collision detection (§9)
# ══════════════════════════════════════════════════════════════════════


class TestVocabCollisionDetection:
    """Vocab collision detection via embedding similarity."""

    def test_no_collision_without_embedder(self):
        store = SQLiteSTLStore()
        result = store.check_vocab_collision("new_word")
        assert result == []

    def test_no_collision_with_different_embeddings(self):
        store = SQLiteSTLStore()
        embedder = MagicMock()
        # Return very different vectors for different words
        def mock_embed(text):
            if text == "new_word":
                return [1.0, 0.0, 0.0]
            return [0.0, 1.0, 0.0]
        embedder.embed = mock_embed

        result = store.check_vocab_collision("new_word", embedder=embedder)
        assert result == []  # no collision

    def test_collision_detected(self):
        store = SQLiteSTLStore()
        embedder = MagicMock()
        # Return very similar vectors
        def mock_embed(text):
            if text == "new_word":
                return [1.0, 0.0, 0.0]
            if text == "like":  # existing seed word
                return [0.99, 0.1, 0.0]  # very similar
            return [0.0, 0.0, 1.0]
        embedder.embed = mock_embed

        result = store.check_vocab_collision("new_word", embedder=embedder, threshold=0.9)
        # Should find collision with "like"
        collisions = [w for w, s in result if w == "like"]
        assert len(collisions) == 1

    def test_handle_new_pred_with_collision_logging(self, caplog):
        """_handle_new_pred should log warnings for collisions."""
        import logging
        store = SQLiteSTLStore()
        embedder = MagicMock()
        # Always return very similar vectors → collision
        embedder.embed = lambda text: [1.0, 0.0, 0.0]

        with caplog.at_level(logging.WARNING, logger="mind.stl.store"):
            store._handle_new_pred(
                'NEW_PRED obsessed | prop | experiencer,target | extreme liking',
                embedder=embedder,
            )

        # Should have collision warnings + successful registration
        assert any("Vocab collision" in r.message for r in caplog.records)
        # But word should still be registered (soft alert)
        assert store.get_vocab_category("obsessed") == "prop"


# ══════════════════════════════════════════════════════════════════════
# Store coreference & coref_pending methods
# ══════════════════════════════════════════════════════════════════════


class TestStoreCoreference:
    """SQLiteSTLStore coreference and coref_pending methods."""

    def test_insert_coreference(self):
        store = SQLiteSTLStore()
        store.insert_coreference(
            source_expr="he",
            resolved_to="ref_tom",
            turn_id=5,
            confidence=0.85,
            method="focus_stack",
        )
        conn = store._get_conn()
        row = conn.execute("SELECT * FROM coreference WHERE resolved_to = ?", ("ref_tom",)).fetchone()
        assert row is not None
        assert row["source_expr"] == "he"
        assert row["confidence"] == pytest.approx(0.85)
        assert row["method"] == "focus_stack"

    def test_insert_coref_pending(self):
        store = SQLiteSTLStore()
        candidates = [
            {"ref_id": "ref_tom", "score": 0.6},
            {"ref_id": "ref_bob", "score": 0.55},
        ]
        store.insert_coref_pending(
            source_expr="他",
            candidates=candidates,
            turn_id=8,
        )
        import json
        conn = store._get_conn()
        row = conn.execute("SELECT * FROM coref_pending WHERE source_expr = ?", ("他",)).fetchone()
        assert row is not None
        stored_candidates = json.loads(row["candidates"])
        assert len(stored_candidates) == 2
        assert row["status"] == "pending"

    def test_query_recent_refs(self):
        store = SQLiteSTLStore()
        # Insert some refs
        store.upsert_ref("ref1", "named", "person", "tom", [], "owner1")
        store.upsert_ref("ref2", "named", "city", "tokyo", [], "owner1")
        store.upsert_ref("self_owner1", "self", None, None, [], "owner1")

        refs = store.query_recent_refs("owner1")
        assert len(refs) == 2  # self is excluded
        ref_ids = {r["id"] for r in refs}
        assert "ref1" in ref_ids
        assert "ref2" in ref_ids
        assert "self_owner1" not in ref_ids

    def test_query_recent_refs_limit(self):
        store = SQLiteSTLStore()
        for i in range(10):
            store.upsert_ref(f"ref{i}", "named", "person", f"p{i}", [], "owner1")

        refs = store.query_recent_refs("owner1", limit=3)
        assert len(refs) == 3

    def test_get_all_vocab_words(self):
        store = SQLiteSTLStore()
        words = store.get_all_vocab_words()
        # Should have seed vocab — spec §9 defines ~75 predicates
        assert len(words) >= 70
        assert "friend" in words
        assert "believe" in words
        assert "time" in words

    def test_seed_vocab_has_all_spec_domains(self):
        """SEED_VOCAB should cover all 6 semantic domains from v2."""
        from mind.stl.vocab import SEED_VOCAB, SEED_DOMAIN_MAP
        domains = {e.domain for e in SEED_VOCAB}
        assert domains == {"relationships", "attributes", "actions", "attitudes", "logic", "modifiers"}
        # Verify key predicates from each domain
        assert SEED_DOMAIN_MAP["brother"] == "relationships"
        assert SEED_DOMAIN_MAP["spouse"] == "relationships"
        assert SEED_DOMAIN_MAP["nationality"] == "attributes"
        assert SEED_DOMAIN_MAP["work_at"] == "attributes"
        assert SEED_DOMAIN_MAP["birthday"] == "actions"
        assert SEED_DOMAIN_MAP["gift"] == "actions"


# ══════════════════════════════════════════════════════════════════════
# Store temporal specs with anchor_date
# ══════════════════════════════════════════════════════════════════════


class TestStoreTemporalWithAnchor:
    """Integration: time() qualifier resolution stored via _handle_time_qualifier."""

    def test_relative_time_stored_as_resolved(self):
        """When anchor_date is provided, relative time should resolve."""
        store = SQLiteSTLStore()
        store._handle_time_qualifier(
            stmt_id="test_stmt_1",
            args_json=["$p1", "next_month"],
            anchor_turn=5,
            anchor_date=date(2026, 3, 30),
        )
        conn = store._get_conn()
        row = conn.execute(
            "SELECT * FROM temporal_specs WHERE stmt_id = ?", ("test_stmt_1",)
        ).fetchone()
        assert row is not None
        assert row["time_type"] == "point"
        assert row["resolved_start"] == "2026-04"
        assert row["anchor_turn"] == 5

    def test_fuzzy_time_stored_without_resolution(self):
        store = SQLiteSTLStore()
        store._handle_time_qualifier(
            stmt_id="test_stmt_2",
            args_json=["$p1", "recent"],
            anchor_turn=3,
            anchor_date=date(2026, 3, 30),
        )
        conn = store._get_conn()
        row = conn.execute(
            "SELECT * FROM temporal_specs WHERE stmt_id = ?", ("test_stmt_2",)
        ).fetchone()
        assert row is not None
        assert row["time_type"] == "fuzzy"
        assert row["fuzzy_desc"] == "recent"
        assert row["window_days"] == 30


# ══════════════════════════════════════════════════════════════════════
# store_program with anchor_date integration
# ══════════════════════════════════════════════════════════════════════


class TestStoreProgramAnchorDate:
    """store_program should thread anchor_date to time() qualifier resolution."""

    def test_store_program_resolves_relative_time(self):
        """time() qualifiers should be resolved when anchor_date is passed."""
        store = SQLiteSTLStore()
        store.create_conversation("conv1")

        program = ParsedProgram(
            batch_id="b1",
            refs=[
                ParsedRef(local_id="s", expr=RefExpr(scope=RefScope.SELF)),
            ],
            statements=[
                ParsedStatement(
                    local_id="p1",
                    predicate="resign",
                    args=[RefArg(ref_id="s")],
                ),
                ParsedStatement(
                    local_id="p2",
                    predicate="time",
                    args=[PropArg(prop_id="p1"), LiteralArg(value="next_month")],
                ),
            ],
        )

        result = store.store_program(
            program=program,
            owner_id="owner1",
            conv_id="conv1",
            anchor_date=date(2026, 3, 30),
        )

        assert result.statements_inserted == 2
        conn = store._get_conn()
        row = conn.execute(
            "SELECT * FROM temporal_specs WHERE stmt_id = ?", ("b1_p2",)
        ).fetchone()
        assert row is not None
        assert row["time_type"] == "point"
        assert row["resolved_start"] == "2026-04"

    def test_store_program_without_anchor_date_falls_back_to_fuzzy(self):
        """Without anchor_date, relative time should resolve as fuzzy."""
        store = SQLiteSTLStore()
        store.create_conversation("conv2")

        program = ParsedProgram(
            batch_id="b2",
            refs=[
                ParsedRef(local_id="s", expr=RefExpr(scope=RefScope.SELF)),
            ],
            statements=[
                ParsedStatement(
                    local_id="p1",
                    predicate="hobby",
                    args=[RefArg(ref_id="s"), LiteralArg(value="running")],
                ),
                ParsedStatement(
                    local_id="p2",
                    predicate="time",
                    args=[PropArg(prop_id="p1"), LiteralArg(value="recent")],
                ),
            ],
        )

        result = store.store_program(
            program=program,
            owner_id="owner2",
            conv_id="conv2",
        )

        assert result.statements_inserted == 2
        conn = store._get_conn()
        row = conn.execute(
            "SELECT * FROM temporal_specs WHERE stmt_id = ?", ("b2_p2",)
        ).fetchone()
        assert row is not None
        assert row["time_type"] == "fuzzy"
        assert row["fuzzy_desc"] == "recent"
