"""STL Parser — converts LLM text output into a ParsedProgram.

Implements the 4-level cascade from §16 of the spec:
  Level 1 (strict):  regex line-type detection + bracket-matching arg split
  Level 2 (fuzzy):   auto-repair common errors, retry strict
  Level 3 (LLM):     batch failed lines through an LLM for reformatting
  Level 4 (fallback): wrap as note(PARSE_FAIL: ...)

Design invariants:
  - Each line is parsed independently (line-level isolation).
  - Inline predicates are expanded to flat $_autoN statements.
  - $id is local to the batch; globalization happens at storage time.
  - @self is implicitly declared; other @ids must be declared before use.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from mind.stl.models import (
    FailedLine,
    InlinePredArg,
    ListArg,
    LiteralArg,
    NumberArg,
    ParsedArg,
    ParsedEvidence,
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
# Line-type regex patterns (§16)
# ══════════════════════════════════════════════════════════════════════

_RE_COMMENT = re.compile(r"^\s*#")
_RE_REF = re.compile(r"^@(\w+)\s*=\s*(.+)$")
_RE_BLANK_DECL = re.compile(r"^_:(\w+)\s*=\s*_:(\w+)$")
_RE_PROP = re.compile(r"^\$(\w+)\s*=\s*(\w+)\((.+)\)\s*$")
_RE_EV = re.compile(r"^ev\(\$(\w+)\s*,?\s*(.+)\)\s*$")
_RE_NOTE = re.compile(r'^note\(\$(\w+)\s*,\s*"(.+)"\)\s*$')

# Ref expression sub-patterns
_RE_REF_SELF = re.compile(r"^@self$")
_RE_REF_LOCAL = re.compile(r'^@local/(\w+)\("([^"]+)"(?:\s*,\s*alias\s*=\s*(\[.*\]))?\)$')
_RE_REF_WORLD = re.compile(r'^@world/(\w+)\("([^"]+)"(?:\s*,\s*alias\s*=\s*(\[.*\]))?\)$')
_RE_REF_BLANK = re.compile(r"^_:(\w+)$")

# Evidence kv-pair patterns
_RE_KV_CONF = re.compile(r'conf\s*=\s*([\d.]+)')
_RE_KV_SRC = re.compile(r'src\s*=\s*"([^"]*)"')
_RE_KV_SPAN = re.compile(r'span\s*=\s*"([^"]*)"')
_RE_KV_RESIDUAL = re.compile(r'residual\s*=\s*"([^"]*)"')

# Number detection
_RE_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")


# ══════════════════════════════════════════════════════════════════════
# Bracket-matching argument splitter (§16)
# ══════════════════════════════════════════════════════════════════════

def split_args(args_str: str) -> List[str]:
    """Split arguments at top-level commas, respecting brackets and quotes.

    Handles nested parentheses (inline predicates), square brackets (lists),
    and double-quoted strings.
    """
    result: List[str] = []
    current: List[str] = []
    depth = 0
    in_string = False
    prev_ch = ""

    for ch in args_str:
        if ch == '"' and prev_ch != "\\":
            in_string = not in_string
        if not in_string:
            if ch in "([":
                depth += 1
            elif ch in ")]":
                depth -= 1
            elif ch == "," and depth == 0:
                result.append("".join(current).strip())
                current = []
                prev_ch = ch
                continue
        current.append(ch)
        prev_ch = ch

    if current:
        result.append("".join(current).strip())
    return [a for a in result if a]  # drop empty


# ══════════════════════════════════════════════════════════════════════
# Typed argument parser
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

    # [list]
    if token.startswith("[") and token.endswith("]"):
        inner = token[1:-1].strip()
        if not inner:
            return ListArg(items=[])
        items = [parse_arg(item) for item in split_args(inner)]
        return ListArg(items=items)

    # number
    if _RE_NUMBER.match(token):
        return NumberArg(value=float(token))

    # inline predicate: word(args...)
    m = re.match(r"^(\w+)\((.+)\)$", token, re.DOTALL)
    if m:
        pred_name = m.group(1)
        inner_args = split_args(m.group(2))
        parsed_inner = [parse_arg(a) for a in inner_args]
        return InlinePredArg(predicate=pred_name, args=parsed_inner)

    # Fallback: treat as literal (unquoted string)
    return LiteralArg(value=token)


# ══════════════════════════════════════════════════════════════════════
# Ref expression parser
# ══════════════════════════════════════════════════════════════════════

def _parse_alias_list(raw: Optional[str]) -> List[str]:
    """Parse an alias list like '["小汤", "Tommy"]' into a Python list."""
    if not raw:
        return []
    raw = raw.strip()
    if not (raw.startswith("[") and raw.endswith("]")):
        return []
    inner = raw[1:-1].strip()
    if not inner:
        return []
    aliases = []
    for item in split_args(inner):
        item = item.strip()
        if item.startswith('"') and item.endswith('"'):
            aliases.append(item[1:-1])
        else:
            aliases.append(item)
    return aliases


def parse_ref_expr(text: str) -> RefExpr:
    """Parse the right-hand side of a REF line into a RefExpr."""
    text = text.strip()

    if _RE_REF_SELF.match(text):
        return RefExpr(scope=RefScope.SELF)

    m = _RE_REF_LOCAL.match(text)
    if m:
        return RefExpr(
            scope=RefScope.LOCAL,
            ref_type=m.group(1),
            key=m.group(2),
            aliases=_parse_alias_list(m.group(3)),
        )

    m = _RE_REF_WORLD.match(text)
    if m:
        return RefExpr(
            scope=RefScope.WORLD,
            ref_type=m.group(1),
            key=m.group(2),
            aliases=_parse_alias_list(m.group(3)),
        )

    m = _RE_REF_BLANK.match(text)
    if m:
        return RefExpr(scope=RefScope.BLANK, key=m.group(1))

    raise ValueError(f"Cannot parse ref expression: {text!r}")


# ══════════════════════════════════════════════════════════════════════
# Inline predicate expansion
# ══════════════════════════════════════════════════════════════════════

class _AutoIdCounter:
    """Generates sequential $_autoN IDs for inline expansion."""

    def __init__(self) -> None:
        self._n = 0

    def next(self) -> str:
        self._n += 1
        return f"_auto{self._n}"


def expand_inline_predicates(
    stmt: ParsedStatement,
    counter: _AutoIdCounter,
) -> List[ParsedStatement]:
    """Expand inline predicate arguments into separate statements.

    Returns a list of newly generated statements (possibly empty).
    The original statement's args are mutated in place: inline predicates
    are replaced with PropArg references to the generated statements.
    """
    generated: List[ParsedStatement] = []

    new_args: List[ParsedArg] = []
    for arg in stmt.args:
        if isinstance(arg, InlinePredArg):
            # Create a new statement for this inline predicate
            auto_id = counter.next()
            inner_stmt = ParsedStatement(
                local_id=auto_id,
                predicate=arg.predicate,
                args=list(arg.args),
                parse_level=stmt.parse_level,
                is_auto_expanded=True,
            )
            # Recursively expand nested inlines
            generated.extend(expand_inline_predicates(inner_stmt, counter))
            generated.append(inner_stmt)
            # Replace inline arg with a $ref
            new_args.append(PropArg(prop_id=auto_id))
        else:
            new_args.append(arg)

    stmt.args = new_args
    return generated


# ══════════════════════════════════════════════════════════════════════
# Level 1: Strict parse
# ══════════════════════════════════════════════════════════════════════

def _strict_parse_line(line: str) -> Optional[Any]:
    """Attempt strict parse of a single line.

    Returns a parsed object (ParsedRef, ParsedStatement, ParsedEvidence,
    ParsedNote) or None for comments/blank.  Raises ValueError on failure.
    """
    stripped = line.strip()
    if not stripped:
        return None

    # Comment
    if _RE_COMMENT.match(stripped):
        return None

    # REF: @id = ref_expr
    m = _RE_REF.match(stripped)
    if m:
        local_id = m.group(1)
        expr = parse_ref_expr(m.group(2))
        return ParsedRef(local_id=local_id, expr=expr)

    # BLANK DECL: _:id = _:id (blank node self-declaration)
    m = _RE_BLANK_DECL.match(stripped)
    if m:
        local_id = m.group(1)
        expr = RefExpr(scope=RefScope.BLANK, key=local_id)
        return ParsedRef(local_id=local_id, expr=expr)

    # EV: ev($id, kv_pairs)
    m = _RE_EV.match(stripped)
    if m:
        target = m.group(1)
        kv_text = m.group(2)
        conf_m = _RE_KV_CONF.search(kv_text)
        if not conf_m:
            raise ValueError(f"ev() missing conf: {stripped!r}")
        conf = float(conf_m.group(1))
        src_m = _RE_KV_SRC.search(kv_text)
        span_m = _RE_KV_SPAN.search(kv_text)
        residual_m = _RE_KV_RESIDUAL.search(kv_text)
        return ParsedEvidence(
            target_local_id=target,
            conf=conf,
            src=src_m.group(1) if src_m else None,
            span=span_m.group(1) if span_m else None,
            residual=residual_m.group(1) if residual_m else None,
        )

    # NOTE: note($id, "text")
    m = _RE_NOTE.match(stripped)
    if m:
        return ParsedNote(target_local_id=m.group(1), text=m.group(2))

    # PROP/FRAME: $id = predicate(args...)
    m = _RE_PROP.match(stripped)
    if m:
        local_id = m.group(1)
        predicate = m.group(2)
        args_str = m.group(3)
        args = [parse_arg(a) for a in split_args(args_str)]
        return ParsedStatement(local_id=local_id, predicate=predicate, args=args)

    raise ValueError(f"No pattern matched: {stripped!r}")


# ══════════════════════════════════════════════════════════════════════
# Level 2: Fuzzy repair
# ══════════════════════════════════════════════════════════════════════

_FUZZY_TYPOS = {
    "confirm": "conf",
    "souce": "src",
    "source": "src",
    "confidence": "conf",
}


def _fuzzy_repair(line: str) -> str:
    """Apply common auto-repairs to a line.

    Repairs:
    - Chinese quotes → English quotes
    - Known kv-pair typos in ev()
    - Unbalanced trailing parenthesis
    """
    # Chinese quotes → English
    repaired = line.replace("\u201c", '"').replace("\u201d", '"')
    repaired = repaired.replace("\u2018", '"').replace("\u2019", '"')

    # Known typos
    for wrong, correct in _FUZZY_TYPOS.items():
        repaired = repaired.replace(f"{wrong}=", f"{correct}=")

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
    llm_repair_fn: Optional[Callable[[List[str]], List[str]]] = None,
) -> ParsedProgram:
    """Parse an STL text block into a structured ParsedProgram.

    Args:
        text: Raw STL text from the LLM.
        batch_id: Unique extraction batch identifier.
        llm_repair_fn: Optional callback for Level 3 repair.
            Receives a list of failed raw lines, returns repaired lines.
            If None, Level 3 is skipped.

    Returns:
        ParsedProgram with all successfully parsed elements.
    """
    program = ParsedProgram(batch_id=batch_id)
    auto_counter = _AutoIdCounter()
    declared_refs: set = {"self"}  # @self is implicit
    failed_for_llm: List[Tuple[int, str]] = []

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
            failed_for_llm.append((line_num, stripped))
            continue

        if parsed is not None:
            _collect_parsed(parsed, program, auto_counter, declared_refs)

    # Level 3: LLM batch repair
    if failed_for_llm and llm_repair_fn is not None:
        raw_failed = [line for _, line in failed_for_llm]
        try:
            repaired_lines = llm_repair_fn(raw_failed)
        except Exception:
            logger.exception("LLM repair failed; falling through to Level 4")
            repaired_lines = []

        still_failed: List[Tuple[int, str]] = []
        for (line_num, original), repaired in zip(
            failed_for_llm, repaired_lines or []
        ):
            try:
                parsed = _strict_parse_line(repaired.strip())
                if parsed is not None:
                    _set_parse_level(parsed, ParseLevel.LLM_CORRECTED)
                    _collect_parsed(parsed, program, auto_counter, declared_refs)
                else:
                    still_failed.append((line_num, original))
            except (ValueError, IndexError):
                still_failed.append((line_num, original))

        # Any not covered by repaired_lines
        if len(repaired_lines or []) < len(failed_for_llm):
            for ln, orig in failed_for_llm[len(repaired_lines or []) :]:
                still_failed.append((ln, orig))

        failed_for_llm = still_failed

    # Level 4: fallback to NOTE
    for line_num, raw in failed_for_llm:
        # Find nearest statement target for the PARSE_FAIL note
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
    auto_counter: _AutoIdCounter,
    declared_refs: set,
) -> None:
    """Route a successfully parsed object into the program."""
    if isinstance(parsed, ParsedRef):
        program.refs.append(parsed)
        declared_refs.add(parsed.local_id)

    elif isinstance(parsed, ParsedStatement):
        # Expand inline predicates before collecting
        generated = expand_inline_predicates(parsed, auto_counter)
        for g in generated:
            program.statements.append(g)
        program.statements.append(parsed)

        # Check for undeclared ref args — create fallback refs
        _check_undeclared_refs(parsed, program, declared_refs)
        for g in generated:
            _check_undeclared_refs(g, program, declared_refs)

    elif isinstance(parsed, ParsedEvidence):
        program.evidence.append(parsed)

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
