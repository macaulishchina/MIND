"""Parsed AST data models for the Semantic Translation Layer (v2).

These models represent the output of the STL parser — a structured,
type-safe intermediate form ready for storage.

v2 simplifications:
  - Removed ParsedEvidence (EV deleted — system-side inference)
  - Removed ListArg, InlinePredArg (args are 4 atomic types only)
  - Removed scope LOCAL/WORLD/BLANK (unified)
  - Added suggested_pred to ParsedStatement
  - Simplified RefExpr (no aliases, no scope prefixes)
  - Removed LLM_CORRECTED parse level (3-level cascade)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ParseLevel(str, Enum):
    """How a line was successfully parsed (traceability tag)."""
    STRICT = "strict"
    FUZZY = "fuzzy"
    FALLBACK = "fallback"


class RefScope(str, Enum):
    """Scope of an entity reference."""
    SELF = "self"
    NAMED = "named"      # @id: TYPE "key"
    UNNAMED = "unnamed"  # @id: TYPE (no key)
    UNKNOWN = "unknown"  # fallback for undeclared refs


# ---------------------------------------------------------------------------
# Ref Expression
# ---------------------------------------------------------------------------

class RefExpr(BaseModel):
    """Parsed entity reference expression: @id: TYPE or @id: TYPE "key"."""
    scope: RefScope
    ref_type: Optional[str] = None   # "person", "place", etc.
    key: Optional[str] = None        # "tom", "tokyo", etc.


# ---------------------------------------------------------------------------
# Parsed Argument Types — 4 atomic types only (v2)
# ---------------------------------------------------------------------------

class RefArg(BaseModel):
    """Argument referencing an entity: @id."""
    kind: str = "ref"
    ref_id: str   # local alias like "tom", "self"


class PropArg(BaseModel):
    """Argument referencing a proposition/frame: $id."""
    kind: str = "prop"
    prop_id: str  # local alias like "p1", "f1"


class LiteralArg(BaseModel):
    """String literal argument: "text"."""
    kind: str = "literal"
    value: str


class NumberArg(BaseModel):
    """Numeric argument: 42, 0.8."""
    kind: str = "number"
    value: float


# Union type for all argument kinds (v2: 4 atomic types, no nesting)
ParsedArg = Union[RefArg, PropArg, LiteralArg, NumberArg]


# ---------------------------------------------------------------------------
# Parsed Line Types
# ---------------------------------------------------------------------------

class ParsedRef(BaseModel):
    """Parsed REF line: @id: TYPE "key"."""
    local_id: str            # "tom", "p1", etc.
    expr: RefExpr
    parse_level: ParseLevel = ParseLevel.STRICT


class ParsedStatement(BaseModel):
    """Parsed STMT line: $id = predicate(args...)[:suggested_word]."""
    local_id: str            # "p1", "f1", etc.
    predicate: str           # "friend", "hope", etc.
    args: List[ParsedArg]
    suggested_pred: Optional[str] = None  # ":suggested_word" if present
    category: Optional[str] = None  # "prop" | "frame" | "qualifier" — set post-parse
    parse_level: ParseLevel = ParseLevel.STRICT


class ParsedNote(BaseModel):
    """Parsed NOTE line: note($target, "text")."""
    target_local_id: str     # "p1"
    text: str
    parse_level: ParseLevel = ParseLevel.STRICT


class FailedLine(BaseModel):
    """A line that failed all parse levels — preserved for diagnostics."""
    line_number: int
    raw_text: str
    error: str


# ---------------------------------------------------------------------------
# Top-level Parse Result
# ---------------------------------------------------------------------------

class ParsedProgram(BaseModel):
    """Complete parse result for one extraction batch."""
    batch_id: str
    refs: List[ParsedRef] = Field(default_factory=list)
    statements: List[ParsedStatement] = Field(default_factory=list)
    notes: List[ParsedNote] = Field(default_factory=list)
    failed_lines: List[FailedLine] = Field(default_factory=list)

    @property
    def ref_ids(self) -> set:
        """Set of declared local ref IDs."""
        return {r.local_id for r in self.refs}


# ---------------------------------------------------------------------------
# Storage Result
# ---------------------------------------------------------------------------

class StorageResult(BaseModel):
    """Summary of what was persisted from one ParsedProgram."""
    batch_id: str
    refs_upserted: int = 0
    statements_inserted: int = 0
    notes_inserted: int = 0
    vocab_registered: int = 0
    errors: List[str] = Field(default_factory=list)
