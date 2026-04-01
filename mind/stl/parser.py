"""STL v2 Parser — converts LLM text output into a ParsedProgram.

Implements a 3-level cascade:
  Level 1 (strict):  regex line-type detection + comma-split args
  Level 2 (fuzzy):   auto-repair common errors, retry strict
  Level 3 (fallback): wrap as note(PARSE_FAIL: ...)

v2 design invariants:
  - Each line is parsed independently (line-level isolation).
  - No inline predicates — args are 4 atomic types only.
  - No list syntax — multi-value is multiple STMTs.
  - No EV lines — evidence is system-side.
  - REF syntax: @id: TYPE "key" (not @id = @local/TYPE("key"))
  - STMT syntax: $id = pred(args...)[:suggested_word]
  - @self is implicitly declared; other @ids must be declared before use.
"""

from __future__ import annotations

import logging
import re
from typing import Any, List, Optional, Tuple

from mind.stl.models import (
    FailedLine,
    LiteralArg,
    NumberArg,
    ParsedArg,
    ParsedNote,
    ParsedProgram,
    ParsedRef,
    ParsedStatement,
    ParseLevel,
    PropArg,
    RefArg,
    RefExpr,
    RefScope,
)

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
# Line-type regex patterns (v2)
# ══════════════════════════════════════════════════════════════════════

_RE_COMMENT = re.compile(r"^\s*#")
_RE_REF = re.compile(r'^@(\w+):\s*(\w+)(?:\s+"([^"]*)")?\s*$')
_RE_STMT = re.compile(r"^\$(\w+)\s*=\s*(\w+)\((.+)\)(?::(\w+))?\s*$")
_RE_NOTE = re.compile(r'^note\(\$(\w+)\s*,\s*"(.+)"\)\s*$')

# Number detection
_RE_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")


# ══════════════════════════════════════════════════════════════════════
# Argument splitter — comma split respecting quoted strings only
# ══════════════════════════════════════════════════════════════════════

def split_args(args_str: str) -> List[str]:
    """Split arguments at top-level commas, respecting double-quoted strings.

    v2: No nested parentheses or brackets to handle — just string quoting.
    """
    result: List[str] = []
    current: List[str] = []
    in_string = False

    for ch in args_str:
        if ch == '"':
            in_string = not in_string
        if ch == "," and not in_string:
            result.append("".join(current).strip())
            current = []
            continue
        current.append(ch)

    if current:
        result.append("".join(current).strip())
    return [a for a in result if a]  # drop empty


# ══════════════════════════════════════════════════════════════════════
# Typed argument parser — 4 atomic types only
# ══════════════════════════════════════════════════════════════════════

def parse_arg(token: str) -> ParsedArg:
    """Classify a single argument token into its typed representation."""
    token = token.strip()

    # @ref
    if token.startswith("@"):
        return RefArg(ref_id=token[1:])

    # $prop
    if token.startswith("$"):
        return PropArg(prop_id=token[1:])

    # "literal"
    if token.startswith('"') and token.endswith('"'):
        return LiteralArg(value=token[1:-1])

    # number
    if _RE_NUMBER.match(token):
        return NumberArg(value=float(token))

    # Fallback: treat as literal (unquoted string)
    return LiteralArg(value=token)


# ══════════════════════════════════════════════════════════════════════
# Level 1: Strict parse
# ══════════════════════════════════════════════════════════════════════

def _strict_parse_line(line: str) -> Optional[Any]:
    """Attempt strict parse of a single line.

    Returns a parsed object (ParsedRef, ParsedStatement, ParsedNote)
    or None for comments/blank.  Raises ValueError on failure.
    """
    stripped = line.strip()
    if not stripped:
        return None

    # Comment
    if _RE_COMMENT.match(stripped):
        return None

    # REF: @id: TYPE "key" or @id: TYPE
    m = _RE_REF.match(stripped)
    if m:
        local_id = m.group(1)
        ref_type = m.group(2)
        key = m.group(3)  # None if no key
        # @self: ... is illegal
        if local_id == "self":
            raise ValueError("@self cannot be declared as a REF")
        scope = RefScope.NAMED if key is not None else RefScope.UNNAMED
        expr = RefExpr(scope=scope, ref_type=ref_type, key=key)
        return ParsedRef(local_id=local_id, expr=expr)

    # NOTE: note($id, "text")
    m = _RE_NOTE.match(stripped)
    if m:
        return ParsedNote(target_local_id=m.group(1), text=m.group(2))

    # STMT: $id = pred(args...)[:suggested]
    m = _RE_STMT.match(stripped)
    if m:
        local_id = m.group(1)
        predicate = m.group(2)
        args_str = m.group(3)
        suggested = m.group(4)  # None if no :suggested
        args = [parse_arg(a) for a in split_args(args_str)]
        return ParsedStatement(
            local_id=local_id,
            predicate=predicate,
            args=args,
            suggested_pred=suggested,
        )

    raise ValueError(f"No pattern matched: {stripped!r}")


# ══════════════════════════════════════════════════════════════════════
# Level 2: Fuzzy repair
# ══════════════════════════════════════════════════════════════════════

def _fuzzy_repair(line: str) -> str:
    """Apply common auto-repairs to a line.

    Repairs:
    - Chinese quotes → English quotes
    - Unbalanced trailing parenthesis
    """
    # Chinese quotes → English
    repaired = line.replace("\u201c", '"').replace("\u201d", '"')
    repaired = repaired.replace("\u2018", '"').replace("\u2019", '"')

    # Balance parentheses: count unmatched
    open_count = repaired.count("(") - repaired.count(")")
    if open_count > 0:
        repaired = repaired.rstrip() + ")" * open_count
    elif open_count < 0:
        # Extra closing parens — try trimming from end
        for _ in range(-open_count):
            idx = repaired.rfind(")")
            if idx >= 0:
                repaired = repaired[:idx] + repaired[idx + 1 :]

    return repaired


# ══════════════════════════════════════════════════════════════════════
# Main parse entry point
# ══════════════════════════════════════════════════════════════════════

def parse_program(
    text: str,
    batch_id: str,
) -> ParsedProgram:
    """Parse an STL v2 text block into a structured ParsedProgram.

    Args:
        text: Raw STL text from the LLM.
        batch_id: Unique extraction batch identifier.

    Returns:
        ParsedProgram with all successfully parsed elements.
    """
    program = ParsedProgram(batch_id=batch_id)
    declared_refs: set = {"self"}  # @self is implicit
    failed_lines: List[Tuple[int, str]] = []

    lines = text.split("\n")

    for line_num, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue

        # Level 1: strict parse
        parsed = None
        try:
            parsed = _strict_parse_line(stripped)
        except (ValueError, IndexError):
            pass

        # Level 2: fuzzy repair
        if parsed is None and stripped:
            repaired = _fuzzy_repair(stripped)
            if repaired != stripped:
                try:
                    parsed = _strict_parse_line(repaired)
                    if parsed is not None:
                        _set_parse_level(parsed, ParseLevel.FUZZY)
                except (ValueError, IndexError):
                    pass

        if parsed is None and stripped and not _RE_COMMENT.match(stripped):
            failed_lines.append((line_num, stripped))
            continue

        if parsed is not None:
            _collect_parsed(parsed, program, declared_refs)

    # Level 3: fallback to NOTE
    for line_num, raw in failed_lines:
        nearest_id = _nearest_statement_id(program)
        if nearest_id:
            program.notes.append(
                ParsedNote(
                    target_local_id=nearest_id,
                    text=f"PARSE_FAIL: {raw}",
                    parse_level=ParseLevel.FALLBACK,
                )
            )
        program.failed_lines.append(
            FailedLine(line_number=line_num, raw_text=raw, error="all levels failed")
        )

    return program


# ══════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════

def _set_parse_level(parsed: Any, level: ParseLevel) -> None:
    """Set parse_level on a parsed object if it has the attribute."""
    if hasattr(parsed, "parse_level"):
        parsed.parse_level = level


def _collect_parsed(
    parsed: Any,
    program: ParsedProgram,
    declared_refs: set,
) -> None:
    """Route a successfully parsed object into the program."""
    if isinstance(parsed, ParsedRef):
        program.refs.append(parsed)
        declared_refs.add(parsed.local_id)

    elif isinstance(parsed, ParsedStatement):
        program.statements.append(parsed)
        # Check for undeclared ref args — create fallback refs
        _check_undeclared_refs(parsed, program, declared_refs)

    elif isinstance(parsed, ParsedNote):
        program.notes.append(parsed)


def _check_undeclared_refs(
    stmt: ParsedStatement,
    program: ParsedProgram,
    declared_refs: set,
) -> None:
    """Create fallback refs for any undeclared @ids in a statement."""
    for arg in stmt.args:
        if isinstance(arg, RefArg) and arg.ref_id not in declared_refs:
            fallback = ParsedRef(
                local_id=arg.ref_id,
                expr=RefExpr(scope=RefScope.UNKNOWN),
                parse_level=ParseLevel.FALLBACK,
            )
            program.refs.append(fallback)
            declared_refs.add(arg.ref_id)


def _nearest_statement_id(program: ParsedProgram) -> Optional[str]:
    """Return the local_id of the most recently added statement, or None."""
    if program.statements:
        return program.statements[-1].local_id
    if program.refs:
        return program.refs[-1].local_id
    return None
