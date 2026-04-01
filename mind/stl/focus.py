"""Focus Stack for coreference resolution.

Implements §17 of the Semantic Translation Layer spec.
Tracks entity salience across conversation turns and provides
top-k active entities for prompt injection.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from mind.stl.models import ParsedProgram, RefScope

logger = logging.getLogger(__name__)

# ── Scoring parameters (§17) ────────────────────────────────────────

# Weight vector: S(e) = 0.35*R + 0.20*F + 0.20*G + 0.15*T + 0.10*P
W_RECENCY = 0.35
W_FREQUENCY = 0.20
W_GRAMMAR = 0.20
W_TOPIC = 0.15
W_SPEAKER = 0.10

# Recency decay base
RECENCY_DECAY = 0.78

# Grammar role scores
GRAMMAR_SUBJECT = 1.0
GRAMMAR_OBJECT = 0.6
GRAMMAR_OTHER = 0.3

# Frequency cap
FREQUENCY_CAP = 10

# Speaker proximity bonuses
SPEAKER_MENTIONED_BOOST = 0.1
SPEAKER_SELF_BOOST = 0.2

# Ambiguity / acceptance thresholds
AMBIGUITY_MARGIN = 0.12
AUTO_ACCEPT_THRESHOLD = 0.62
EXPLICIT_MENTION_BOOST = 0.35
LONG_GAP_PENALTY = -0.15
LONG_GAP_TURNS = 8

# Default top-k
DEFAULT_TOP_K = 5


@dataclass
class FocusEntry:
    """A single entity tracked in the focus stack."""

    ref_id: str
    ref_expr: str  # e.g. '@local/person("tom")'
    score: float = 0.0
    last_mentioned_turn: int = 0
    mention_count: int = 0
    # Internal scoring components (not exposed to prompt)
    _grammar_role: float = field(default=GRAMMAR_OTHER, repr=False)
    _is_speaker_mentioned: bool = field(default=False, repr=False)
    _is_speaker_self: bool = field(default=False, repr=False)


class FocusStack:
    """Tracks entity salience across conversation turns.

    The stack maintains a scored list of entities.  Before each LLM
    extraction call, ``top_k_for_prompt()`` returns the most salient
    entities in a format ready for ``format_focus_stack()``.

    After extraction, ``update()`` refreshes scores based on what the
    LLM produced.
    """

    def __init__(self, top_k: int = DEFAULT_TOP_K) -> None:
        self.top_k = top_k
        self._entries: Dict[str, FocusEntry] = {}

    @property
    def entries(self) -> List[FocusEntry]:
        """All entries sorted by score descending."""
        return sorted(self._entries.values(), key=lambda e: e.score, reverse=True)

    def bootstrap_from_refs(
        self,
        refs: List[Dict],
        current_turn: int,
    ) -> None:
        """Seed the focus stack from stored ref rows.

        Each dict should have keys: ``id``, ``scope``, ``ref_type``,
        ``key``, ``aliases``.
        """
        for ref_row in refs:
            ref_id = ref_row["id"]
            if ref_id in self._entries:
                continue
            scope = ref_row.get("scope", "local")
            if scope == "self":
                continue  # @self is implicit, not tracked in focus
            ref_type = ref_row.get("ref_type", "")
            key = ref_row.get("key", "")
            ref_expr = f"@{scope}/{ref_type}(\"{key}\")" if ref_type else f"@{scope}(\"{key}\")"
            self._entries[ref_id] = FocusEntry(
                ref_id=ref_id,
                ref_expr=ref_expr,
                last_mentioned_turn=0,
                mention_count=1,
            )
        self._recompute_scores(current_turn)

    def update(
        self,
        program: ParsedProgram,
        current_turn: int,
        ref_map: Optional[Dict[str, str]] = None,
    ) -> None:
        """Update the focus stack after an extraction.

        Scans the parsed program for entity mentions and updates
        recency, frequency, and grammar role for each referenced entity.

        Args:
            program: The parsed STL program from this extraction.
            current_turn: The turn number of the current conversation.
            ref_map: Mapping from local @id to global ref ID (from store_program).
        """
        if ref_map is None:
            ref_map = {}

        # Collect mentioned ref IDs and their positions
        mentioned: Dict[str, _MentionInfo] = {}

        for ref in program.refs:
            if ref.expr.scope == RefScope.SELF:
                continue
            global_id = ref_map.get(ref.local_id, ref.local_id)
            ref_type = ref.expr.ref_type or ""
            key = ref.expr.key or ""
            if key:
                ref_expr = f'@{ref.local_id}: {ref_type} "{key}"'
            elif ref_type:
                ref_expr = f"@{ref.local_id}: {ref_type}"
            else:
                ref_expr = f"@{ref.local_id}"
            if global_id not in mentioned:
                mentioned[global_id] = _MentionInfo(ref_expr=ref_expr)

        # Scan statements for grammar role inference
        for stmt in program.statements:
            for pos, arg in enumerate(stmt.args):
                kind = getattr(arg, "kind", None)
                if kind != "ref":
                    continue
                local_id = arg.ref_id
                global_id = ref_map.get(local_id, local_id)
                if global_id not in mentioned:
                    # Entity referenced but not declared in this batch
                    # (could be @self or a previously declared entity)
                    continue
                info = mentioned[global_id]
                info.mention_count += 1
                # Position 0 → subject, position 1+ → object/other
                if pos == 0:
                    info.max_grammar = max(info.max_grammar, GRAMMAR_SUBJECT)
                elif pos == 1:
                    info.max_grammar = max(info.max_grammar, GRAMMAR_OBJECT)
                else:
                    info.max_grammar = max(info.max_grammar, GRAMMAR_OTHER)

        # Apply updates
        for global_id, info in mentioned.items():
            entry = self._entries.get(global_id)
            if entry is None:
                entry = FocusEntry(
                    ref_id=global_id,
                    ref_expr=info.ref_expr,
                )
                self._entries[global_id] = entry
            entry.last_mentioned_turn = current_turn
            entry.mention_count += info.mention_count
            entry._grammar_role = info.max_grammar
            entry._is_speaker_mentioned = info.mention_count > 0

        self._recompute_scores(current_turn)

    def _recompute_scores(self, current_turn: int) -> None:
        """Recompute all entity scores with the 5-dimension formula."""
        for entry in self._entries.values():
            gap = current_turn - entry.last_mentioned_turn

            # R: Recency = 0.78^gap
            r = RECENCY_DECAY ** gap

            # F: Frequency = min(1.0, count / 10)
            f = min(1.0, entry.mention_count / FREQUENCY_CAP)

            # G: Grammar role
            g = entry._grammar_role

            # T: Topic relevance — placeholder (requires embedding similarity)
            t = 0.5

            # P: Speaker proximity
            p = 0.0
            if entry._is_speaker_self:
                p = SPEAKER_SELF_BOOST
            elif entry._is_speaker_mentioned:
                p = SPEAKER_MENTIONED_BOOST

            score = W_RECENCY * r + W_FREQUENCY * f + W_GRAMMAR * g + W_TOPIC * t + W_SPEAKER * p

            # Long gap penalty
            if gap > LONG_GAP_TURNS:
                score += LONG_GAP_PENALTY

            entry.score = max(0.0, score)

    def top_k_for_prompt(self) -> List[Dict]:
        """Return top-k entries formatted for ``format_focus_stack()``.

        Returns:
            List of dicts with ``ref_expr``, ``score``, ``last_mentioned_turn``.
        """
        ranked = self.entries[: self.top_k]
        return [
            {
                "ref_expr": e.ref_expr,
                "score": round(e.score, 2),
                "last_mentioned_turn": e.last_mentioned_turn,
            }
            for e in ranked
            if e.score > 0
        ]

    def resolve_ambiguous(self, top1_id: str, top2_id: str) -> Optional[str]:
        """Check if top-1 is clearly the best, or if it's ambiguous.

        Returns the resolved ref_id if unambiguous, None if ambiguous.
        """
        e1 = self._entries.get(top1_id)
        e2 = self._entries.get(top2_id)
        if e1 is None:
            return None
        if e2 is None:
            return top1_id
        if e1.score >= AUTO_ACCEPT_THRESHOLD and (e1.score - e2.score) >= AMBIGUITY_MARGIN:
            return top1_id
        return None  # ambiguous


@dataclass
class _MentionInfo:
    """Internal helper to accumulate mention data during update()."""

    ref_expr: str = ""
    mention_count: int = 0
    max_grammar: float = GRAMMAR_OTHER
