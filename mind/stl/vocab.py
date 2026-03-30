"""Seed vocabulary for the Semantic Translation Layer.

Contains ~30 predefined predicates grouped by category (prop, frame, qualifier).
These are pre-populated into ``vocab_registry`` on store initialization,
following §9 of the spec.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional


class SeedEntry(NamedTuple):
    word: str
    category: str            # "prop" | "frame" | "qualifier"
    arg_schema: Optional[str]
    definition: str


# ── Frame seed predicates (~20) ──────────────────────────────────────
# Organized by sub-category per §9

_FRAME_COGNITIVE = [
    SeedEntry("believe", "frame", "experiencer,content", "epistemic belief"),
    SeedEntry("doubt", "frame", "experiencer,content", "epistemic doubt"),
    SeedEntry("know", "frame", "experiencer,content", "epistemic knowledge"),
    SeedEntry("uncertain", "frame", "experiencer,content", "epistemic uncertainty"),
]

_FRAME_VOLITIONAL = [
    SeedEntry("hope", "frame", "experiencer,content", "volitional hope"),
    SeedEntry("want", "frame", "experiencer,content", "volitional desire"),
    SeedEntry("intend", "frame", "experiencer,content", "volitional intention"),
]

_FRAME_SPEECH = [
    SeedEntry("say", "frame", "speaker,content", "speech act: report"),
    SeedEntry("recommend", "frame", "speaker,content", "speech act: recommendation"),
    SeedEntry("ask", "frame", "speaker,content", "speech act: question"),
    SeedEntry("promise", "frame", "speaker,content", "speech act: promise"),
]

_FRAME_LOGIC = [
    SeedEntry("if", "frame", "condition,consequence", "conditional"),
    SeedEntry("cause", "frame", "cause,effect", "causal relation"),
    SeedEntry("because", "frame", "effect,cause", "causal explanation"),
]

_FRAME_DEONTIC = [
    SeedEntry("must", "frame", "obligee,content", "deontic obligation"),
    SeedEntry("permit", "frame", "authority,content", "deontic permission"),
    SeedEntry("should", "frame", "obligee,content", "deontic suggestion"),
]

_FRAME_TRUTH = [
    SeedEntry("neg", "frame", "content", "negation"),
    SeedEntry("lie", "frame", "speaker,content", "false narrative"),
    SeedEntry("joke", "frame", "speaker,content", "humorous/non-serious"),
    SeedEntry("retract_intent", "frame", "speaker,content", "retraction intent"),
    SeedEntry("correct_intent", "frame", "speaker,content", "correction intent"),
]

_FRAME_EMOTION = [
    SeedEntry("emotion", "frame", "experiencer,emotion_type", "emotional state"),
]

_FRAME_DECISION = [
    SeedEntry("decide", "frame", "agent,content", "decision made"),
    SeedEntry("defer", "frame", "agent,content", "decision deferred"),
    SeedEntry("undecided", "frame", "agent,content", "decision pending"),
]

# ── Qualifier seed predicates (~6) ───────────────────────────────────

_QUALIFIERS = [
    SeedEntry("time", "qualifier", "target,value", "temporal anchor"),
    SeedEntry("degree", "qualifier", "target,value", "degree modifier"),
    SeedEntry("quantity", "qualifier", "target,value", "quantity modifier"),
    SeedEntry("frequency", "qualifier", "target,value", "frequency modifier"),
    SeedEntry("duration", "qualifier", "target,value", "duration modifier"),
    SeedEntry("location", "qualifier", "target,ref_or_value", "location modifier"),
]

# ── Common prop seed predicates ──────────────────────────────────────
# Small set of very common propositions (not exhaustive — LLM creates more)

_PROPS = [
    SeedEntry("friend", "prop", "person1,person2", "friendship relation"),
    SeedEntry("occupation", "prop", "person,job", "occupation/job"),
    SeedEntry("live_in", "prop", "person,place", "residence"),
    SeedEntry("like", "prop", "experiencer,target", "preference"),
    SeedEntry("hobby", "prop", "person,activity", "hobby/interest"),
    SeedEntry("mother", "prop", "child,parent", "mother relation"),
    SeedEntry("father", "prop", "child,parent", "father relation"),
    SeedEntry("resign", "prop", "person", "resignation"),
    SeedEntry("visit", "prop", "visitor,destination", "visit/travel"),
    SeedEntry("plan", "prop", "agent,content", "plan/intention content"),
]

# ── Aggregate ────────────────────────────────────────────────────────

SEED_VOCAB: List[SeedEntry] = (
    _FRAME_COGNITIVE
    + _FRAME_VOLITIONAL
    + _FRAME_SPEECH
    + _FRAME_LOGIC
    + _FRAME_DEONTIC
    + _FRAME_TRUTH
    + _FRAME_EMOTION
    + _FRAME_DECISION
    + _QUALIFIERS
    + _PROPS
)

# Fast lookup: word → category
SEED_CATEGORY_MAP: Dict[str, str] = {e.word: e.category for e in SEED_VOCAB}

# Set of qualifier predicate names for quick checks
QUALIFIER_PREDICATES: set = {e.word for e in _QUALIFIERS}

# Set of correction-related predicates
CORRECTION_PREDICATES: set = {"correct_intent", "retract_intent"}
