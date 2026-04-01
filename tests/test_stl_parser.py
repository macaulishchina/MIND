"""Tests for the STL v2 parser — covers all 3+1 line types, cascade levels,
and examples from the v2 spec."""

import pytest

from mind.stl.parser import parse_program, split_args, parse_arg
from mind.stl.models import (
    ParseLevel,
    RefScope,
    ParsedProgram,
    ParsedRef,
    ParsedStatement,
    ParsedNote,
    FailedLine,
    RefArg,
    PropArg,
    LiteralArg,
    NumberArg,
)


# ══════════════════════════════════════════════════════════════════════
# split_args
# ══════════════════════════════════════════════════════════════════════

class TestSplitArgs:
    def test_simple(self):
        assert split_args('@self, "hello", 42') == ["@self", '"hello"', "42"]

    def test_quoted_comma(self):
        assert split_args('"a, b", @t') == ['"a, b"', "@t"]

    def test_empty(self):
        assert split_args("") == []

    def test_multiple_refs(self):
        assert split_args("@self, @tom") == ["@self", "@tom"]

    def test_prop_and_literal(self):
        assert split_args('$p1, "next_month"') == ["$p1", '"next_month"']


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

    def test_unquoted_fallback(self):
        """Unquoted non-number text should become LiteralArg."""
        arg = parse_arg("football_player")
        assert isinstance(arg, LiteralArg)
        assert arg.value == "football_player"


# ══════════════════════════════════════════════════════════════════════
# parse_program — full programs from v2 spec examples
# ══════════════════════════════════════════════════════════════════════

class TestParseProgram:
    def test_simple_relationship(self):
        """Simple relationship + attribute"""
        text = """\
@tom: person "tom"
$p1 = friend(@self, @tom)
$p2 = occupation(@tom, "football_player")
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.refs) == 1
        assert len(prog.statements) == 2
        assert prog.statements[0].predicate == "friend"
        assert prog.statements[1].predicate == "occupation"
        assert prog.refs[0].expr.scope == RefScope.NAMED
        assert prog.refs[0].expr.ref_type == "person"
        assert prog.refs[0].expr.key == "tom"

    def test_unnamed_entity(self):
        """Unnamed entity (no key)"""
        text = """\
@p1: person
$p1 = friend(@self, @p1)
$p2 = occupation(@p1, "football_player")
"""
        prog = parse_program(text, batch_id="test_batch")
        unnamed = [r for r in prog.refs if r.expr.scope == RefScope.UNNAMED]
        assert len(unnamed) == 1
        assert len(prog.statements) == 2

    def test_multivalue_expanded(self):
        """Multi-value expanded form"""
        text = """\
$p1 = speak(@self, "中文")
$p2 = speak(@self, "英语")
$p3 = speak(@self, "日语")
$p4 = degree($p3, "slight")
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.statements) == 4
        preds = [s.predicate for s in prog.statements]
        assert preds.count("speak") == 3
        assert "degree" in preds

    def test_hope_with_intermediate_id(self):
        """Nested meaning via intermediate $id"""
        text = """\
@tom: person "tom"
@tokyo: place "tokyo"
$p1 = visit(@self, @tokyo)
$f1 = hope(@self, $p1)
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.refs) == 2
        assert len(prog.statements) == 2
        hope_stmt = [s for s in prog.statements if s.predicate == "hope"][0]
        assert any(getattr(a, "kind", None) == "prop" for a in hope_stmt.args)

    def test_suggested_pred(self):
        """Suggested predicate via :suffix"""
        text = """\
@tom: person "tom"
$p1 = friend(@self, @tom):childhood_friend
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.statements) == 1
        assert prog.statements[0].predicate == "friend"
        assert prog.statements[0].suggested_pred == "childhood_friend"

    def test_alias_as_stmt(self):
        """alias is a STMT predicate"""
        text = """\
@tom: person "tom"
$a1 = alias(@tom, "小汤")
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.statements) == 1
        assert prog.statements[0].predicate == "alias"

    def test_note(self):
        """NOTE parsing"""
        text = """\
$p1 = resign(@self)
note($p1, "用户说这句话时笑了")
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.notes) == 1
        assert prog.notes[0].target_local_id == "p1"
        assert "笑了" in prog.notes[0].text

    def test_comments_ignored(self):
        text = """\
# This is a comment
@tom: person "tom"
# Another comment
$p1 = name(@tom, "Tom")
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.statements) == 1
        assert len(prog.failed_lines) == 0

    def test_empty_lines_ignored(self):
        text = """\

@tom: person "tom"

$p1 = name(@tom, "Tom")

"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.statements) == 1

    def test_fuzzy_repair_chinese_quotes(self):
        """Level 2: Chinese quotes should be repaired."""
        text = """\
@tom: person \u201ctom\u201d
$p1 = friend(@self, @tom)
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.refs) >= 1  # Should parse after fuzzy repair

    def test_fuzzy_repair_unbalanced_parens(self):
        """Level 2: Missing closing paren should be repaired."""
        text = """\
$p1 = name(@self, "Alice"
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.statements) == 1

    def test_parse_level_tracking(self):
        """Easy lines should be STRICT."""
        text = """\
@tom: person "tom"
$p1 = name(@tom, "Tom")
"""
        prog = parse_program(text, batch_id="test_batch")
        assert prog.refs[0].parse_level == ParseLevel.STRICT
        assert prog.statements[0].parse_level == ParseLevel.STRICT

    def test_failed_lines(self):
        """Unparseable lines should become FailedLine/notes."""
        text = """\
this is not valid STL syntax at all
$p1 = name(@self, "Alice")
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.failed_lines) == 1
        assert "this is not valid" in prog.failed_lines[0].raw_text

    def test_batch_id_propagated(self):
        text = '$p1 = name(@self, "Alice")'
        prog = parse_program(text, batch_id="my_batch_123")
        assert prog.batch_id == "my_batch_123"

    def test_ref_ids_property(self):
        text = """\
@tom: person "tom"
$p1 = friend(@self, @tom)
"""
        prog = parse_program(text, batch_id="test_batch")
        ids = prog.ref_ids
        assert "tom" in ids

    def test_self_cannot_be_declared(self):
        """@self: ... should fail — @self is implicit."""
        text = """\
@self: person "me"
$p1 = name(@self, "Alice")
"""
        prog = parse_program(text, batch_id="test_batch")
        # @self declaration should fail, leaving it as a failed line
        named_self = [r for r in prog.refs if r.local_id == "self"]
        assert len(named_self) == 0

    def test_undeclared_ref_creates_fallback(self):
        """Undeclared @id should create fallback ref."""
        text = '$p1 = friend(@self, @unknown_person)'
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.statements) == 1
        fallback_refs = [r for r in prog.refs if r.local_id == "unknown_person"]
        assert len(fallback_refs) == 1
        assert fallback_refs[0].expr.scope == RefScope.UNKNOWN
        assert fallback_refs[0].parse_level == ParseLevel.FALLBACK

    def test_number_arg(self):
        text = '$p1 = age(@self, 30)'
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.statements) == 1
        age_arg = prog.statements[0].args[1]
        assert isinstance(age_arg, NumberArg)
        assert age_arg.value == 30

    def test_modifier_with_prop_ref(self):
        """Modifier predicates with $id first arg"""
        text = """\
@tom: person "tom"
$p1 = resign(@tom)
$p2 = time($p1, "next_month")
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.statements) == 2
        time_stmt = [s for s in prog.statements if s.predicate == "time"][0]
        assert isinstance(time_stmt.args[0], PropArg)


# ══════════════════════════════════════════════════════════════════════
# Edge cases
# ══════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_self_implicit_ref(self):
        """@self should be usable without explicit declaration."""
        text = '$p1 = name(@self, "Alice")'
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.statements) == 1

    def test_long_program(self):
        """Large program should parse without errors."""
        text = """\
@tom: person "tom"
@sarah: person "sarah"
@mom: person "妈妈"
@mk: place "樱花亭"

$p1 = friend(@self, @tom)
$p2 = visit(@self, @mk)
$p3 = time($p2, "today_noon")

$p4 = plan(@tom, "resign")
$p5 = time($p4, "next_month")
$f1 = say(@tom, $p4)

$p10 = spouse(@tom, @sarah)
$a1 = alias(@tom, "小汤")
note($f1, "Tom 说话时有点犹豫")
"""
        prog = parse_program(text, batch_id="test_batch")
        assert len(prog.refs) == 4
        assert len(prog.statements) >= 7
        assert len(prog.notes) == 1
        assert len(prog.failed_lines) == 0
