"""Tests for the STL parser — covers all 5 line types, cascade levels,
inline expansion, and examples from §11 of the spec."""

import pytest

from mind.stl.parser import parse_program, split_args, parse_arg, parse_ref_expr
from mind.stl.models import (
    ParseLevel,
    RefScope,
    ParsedProgram,
    ParsedRef,
    ParsedStatement,
    ParsedEvidence,
    ParsedNote,
    FailedLine,
    RefArg,
    PropArg,
    LiteralArg,
    NumberArg,
    ListArg,
    InlinePredArg,
)


# ══════════════════════════════════════════════════════════════════════
# split_args
# ══════════════════════════════════════════════════════════════════════

class TestSplitArgs:
    def test_simple(self):
        assert split_args('@s, "hello", 42') == ["@s", '"hello"', "42"]

    def test_nested_parens(self):
        assert split_args('@s, neg(rain("tomorrow"))') == ["@s", 'neg(rain("tomorrow"))']

    def test_list_arg(self):
        assert split_args('@s, ["a", "b"]') == ["@s", '["a", "b"]']

    def test_quoted_comma(self):
        assert split_args('"a, b", @t') == ['"a, b"', "@t"]

    def test_empty(self):
        assert split_args("") == []


# ══════════════════════════════════════════════════════════════════════
# parse_arg
# ══════════════════════════════════════════════════════════════════════

class TestParseArg:
    def test_ref_arg(self):
        arg = parse_arg("@tom")
        assert isinstance(arg, RefArg)
        assert arg.ref_id == "tom"

    def test_prop_arg(self):
        arg = parse_arg("$p1")
        assert isinstance(arg, PropArg)
        assert arg.prop_id == "p1"

    def test_literal(self):
        arg = parse_arg('"hello world"')
        assert isinstance(arg, LiteralArg)
        assert arg.value == "hello world"

    def test_number_int(self):
        arg = parse_arg("42")
        assert isinstance(arg, NumberArg)
        assert arg.value == 42

    def test_number_float(self):
        arg = parse_arg("0.85")
        assert isinstance(arg, NumberArg)
        assert arg.value == 0.85

    def test_list_arg(self):
        arg = parse_arg('["a", "b", "c"]')
        assert isinstance(arg, ListArg)
        assert len(arg.items) == 3

    def test_inline_pred(self):
        arg = parse_arg('neg(rain("tomorrow"))')
        assert isinstance(arg, InlinePredArg)
        assert arg.predicate == "neg"


# ══════════════════════════════════════════════════════════════════════
# parse_ref_expr
# ══════════════════════════════════════════════════════════════════════

class TestParseRefExpr:
    def test_self(self):
        expr = parse_ref_expr("@self")
        assert expr.scope == RefScope.SELF

    def test_local(self):
        expr = parse_ref_expr('@local/person("tom")')
        assert expr.scope == RefScope.LOCAL
        assert expr.ref_type == "person"
        assert expr.key == "tom"

    def test_world(self):
        expr = parse_ref_expr('@world/city("tokyo")')
        assert expr.scope == RefScope.WORLD
        assert expr.ref_type == "city"
        assert expr.key == "tokyo"

    def test_blank(self):
        expr = parse_ref_expr("_:p1")
        assert expr.scope == RefScope.BLANK
        assert expr.key == "p1"

    def test_local_with_alias(self):
        expr = parse_ref_expr('@local/person("tom", alias=["tommy", "t"])')
        assert expr.scope == RefScope.LOCAL
        assert "tommy" in expr.aliases


# ══════════════════════════════════════════════════════════════════════
# parse_program — full programs from §11 examples
# ══════════════════════════════════════════════════════════════════════

class TestParseProgram:
    def test_simple_relationship(self):
        """§11.1: 我朋友 Tom 是足球运动员"""
        text = """\
@s = @self
@t = @local/person("tom")
$p1 = friend(@s, @t)
$p2 = occupation(@t, "football_player")
ev($p1, conf=1.0)
ev($p2, conf=1.0)
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.refs) == 2
        assert len(prog.statements) == 2
        assert len(prog.evidence) == 2
        assert prog.statements[0].predicate == "friend"
        assert prog.statements[1].predicate == "occupation"

    def test_blank_node(self):
        """§11.2: 我有个朋友是足球运动员"""
        text = """\
@s = @self
@u = _:p1
$p1 = friend(@s, @u)
$p2 = occupation(@u, "football_player")
ev($p1, conf=1.0)
ev($p2, conf=1.0)
"""
        prog = parse_program(text, batch_id="test_batch")
        # @u should have blank scope
        blank_refs = [r for r in prog.refs if r.expr.scope == RefScope.BLANK]
        assert len(blank_refs) >= 1
        assert len(prog.statements) == 2

    def test_multivalue_expanded(self):
        """§11.3: multi-value expanded form"""
        text = """\
@s = @self
$p1 = speak(@s, "中文")
$p2 = speak(@s, "英语")
$p3 = speak(@s, "日语")
$p4 = degree($p3, "slight")
ev($p1, conf=1.0)
ev($p2, conf=1.0)
ev($p3, conf=1.0)
ev($p4, conf=0.8, span="一点点")
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.statements) == 4
        preds = [s.predicate for s in prog.statements]
        assert preds.count("speak") == 3
        assert "degree" in preds

    def test_hope_frame(self):
        """§11.4: 我希望 Tom 来东京"""
        text = """\
@s = @self
@t = @local/person("tom")
@k = @world/city("tokyo")
$p1 = come(@t, @k)
$f1 = hope(@s, $p1)
ev($f1, conf=0.9)
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.refs) == 3
        assert len(prog.statements) == 2
        hope_stmt = [s for s in prog.statements if s.predicate == "hope"][0]
        # Second arg should be a PropArg referencing $p1
        assert any(getattr(a, "kind", None) == "prop" for a in hope_stmt.args)

    def test_inline_predicate_expansion(self):
        """§11.5: if(neg(rain("tomorrow")), $p1) — inline expansion"""
        text = """\
@s = @self
$p1 = plan(@s, "running")
$f1 = if(neg(rain("tomorrow")), $p1)
ev($f1, conf=0.9)
"""
        prog = parse_program(text, batch_id="test_batch")
        # The inline pred should be expanded
        assert len(prog.statements) >= 2

    def test_evidence_fields(self):
        text = """\
@s = @self
$p1 = resign(@s)
ev($p1, conf=0.6, span="好像")
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.evidence) == 1
        ev = prog.evidence[0]
        assert ev.conf == 0.6
        assert ev.span == "好像"

    def test_note_with_new_pred(self):
        """§11.13: note with NEW_PRED"""
        text = """\
@s = @self
$f1 = obsessed_with(@s, "long_distance_running")
note($f1, "NEW_PRED obsessed_with | frame | experiencer,target | intense recent fascination")
ev($f1, conf=0.8, span="迷上了")
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.notes) == 1
        assert "NEW_PRED" in prog.notes[0].text
        assert len(prog.statements) == 1

    def test_comments_ignored(self):
        text = """\
# This is a comment
@s = @self
# Another comment
$p1 = name(@s, "Alice")
ev($p1, conf=1.0)
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.statements) == 1
        assert len(prog.failed_lines) == 0

    def test_empty_lines_ignored(self):
        text = """\

@s = @self

$p1 = name(@s, "Alice")

ev($p1, conf=1.0)

"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.statements) == 1

    def test_fuzzy_repair_chinese_quotes(self):
        """Level 2: Chinese quotes should be repaired."""
        text = """\
@s = @self
@t = @local/person(\u201ctom\u201d)
$p1 = friend(@s, @t)
ev($p1, conf=1.0, src=\u201cturn_1\u201d)
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.refs) >= 1  # Should parse after fuzzy repair

    def test_parse_level_tracking(self):
        """Easy lines should be STRICT, fuzzy repaired should be FUZZY."""
        text = """\
@s = @self
$p1 = name(@s, "Alice")
ev($p1, conf=1.0)
"""
        prog = parse_program(text, batch_id="test_batch")
        assert prog.refs[0].parse_level == ParseLevel.STRICT
        assert prog.statements[0].parse_level == ParseLevel.STRICT

    def test_failed_lines(self):
        """Unparseable lines should become FailedLine/notes."""
        text = """\
@s = @self
this is not valid STL syntax at all
$p1 = name(@s, "Alice")
ev($p1, conf=1.0)
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.failed_lines) == 1
        assert "this is not valid" in prog.failed_lines[0].raw_text

    def test_batch_id_propagated(self):
        text = "$p1 = name(@self, \"Alice\")\nev($p1, conf=1.0)"
        prog = parse_program(text, batch_id="my_batch_123")
        assert prog.batch_id == "my_batch_123"

    def test_ref_ids_property(self):
        text = """\
@s = @self
@t = @local/person("tom")
$p1 = friend(@s, @t)
ev($p1, conf=1.0)
"""
        prog = parse_program(text, batch_id="test_batch")
        ids = prog.ref_ids
        assert "s" in ids
        assert "t" in ids


# ══════════════════════════════════════════════════════════════════════
# Edge cases
# ══════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_self_implicit_ref(self):
        """@self should be usable without explicit @s = @self."""
        text = '$p1 = name(@self, "Alice")\nev($p1, conf=1.0)'
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.statements) == 1

    def test_long_program(self):
        """§11.14-style: large program should parse without errors."""
        text = """\
@s  = @self
@t  = @local/person("tom")
@sa = @local/person("sarah")
@m  = @local/person("mom")
@mk = @world/place("樱花亭")
@ik = @world/brand("KALLAX")
_:b1 = _:b1

$p1 = eat_together(@s, @t)
$p2 = location($p1, @mk)
$p3 = time($p1, "today_noon")
ev($p1, conf=1.0)
ev($p2, conf=1.0)

$p4 = plan(@t, resign(@t))
$p5 = time($p4, "next_month")
$f1 = say(@t, $p4)
ev($f1, conf=0.85)

$p10 = spouse(@t, @sa)
ev($p10, conf=0.9)
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.refs) >= 6
        assert len(prog.statements) >= 7
        assert len(prog.evidence) >= 4
        assert len(prog.failed_lines) == 0
