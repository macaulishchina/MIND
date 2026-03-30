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
# Full set per §9 of the spec

_PROPS_RELATION = [
    SeedEntry("friend", "prop", "person1,person2", "friendship relation"),
    SeedEntry("mother", "prop", "child,parent", "mother relation"),
    SeedEntry("father", "prop", "child,parent", "father relation"),
    SeedEntry("brother", "prop", "person1,person2", "brother relation"),
    SeedEntry("sister", "prop", "person1,person2", "sister relation"),
    SeedEntry("spouse", "prop", "person1,person2", "spouse relation"),
    SeedEntry("partner", "prop", "person1,person2", "partner relation"),
    SeedEntry("child", "prop", "parent,child", "child relation"),
    SeedEntry("cousin", "prop", "person1,person2", "cousin relation"),
    SeedEntry("coworker", "prop", "person1,person2", "coworker relation"),
    SeedEntry("boss", "prop", "employee,boss", "boss relation"),
    SeedEntry("mentor", "prop", "mentee,mentor", "mentor relation"),
    SeedEntry("student", "prop", "student,institution_or_teacher", "student relation"),
    SeedEntry("roommate", "prop", "person1,person2", "roommate relation"),
    SeedEntry("neighbor", "prop", "person1,person2", "neighbor relation"),
    SeedEntry("classmate", "prop", "person1,person2", "classmate relation"),
    SeedEntry("teammate", "prop", "person1,person2", "teammate relation"),
    SeedEntry("client", "prop", "provider,client", "client relation"),
    SeedEntry("landlord", "prop", "tenant,landlord", "landlord relation"),
    SeedEntry("doctor", "prop", "patient,doctor", "doctor relation"),
    SeedEntry("pet", "prop", "owner,animal", "pet ownership"),
]

_PROPS_ATTRIBUTE = [
    SeedEntry("name", "prop", "entity,value", "name attribute"),
    SeedEntry("age", "prop", "person,value", "age attribute"),
    SeedEntry("occupation", "prop", "person,job", "occupation/job"),
    SeedEntry("workplace", "prop", "person,org", "workplace"),
    SeedEntry("language", "prop", "person,lang", "language spoken"),
    SeedEntry("education", "prop", "person,value", "education background"),
    SeedEntry("nationality", "prop", "person,value", "nationality"),
]

_PROPS_ACTION = [
    SeedEntry("like", "prop", "experiencer,target", "preference"),
    SeedEntry("dislike", "prop", "experiencer,target", "dislike"),
    SeedEntry("habit", "prop", "person,activity", "habitual behavior"),
    SeedEntry("hobby", "prop", "person,activity", "hobby/interest"),
    SeedEntry("skill", "prop", "person,ability", "skill/ability"),
    SeedEntry("own", "prop", "owner,object", "ownership"),
    SeedEntry("use", "prop", "user,object", "usage"),
    SeedEntry("eat", "prop", "person,food", "eating"),
    SeedEntry("drink", "prop", "person,beverage", "drinking"),
    SeedEntry("speak", "prop", "person,language", "language speaking"),
    SeedEntry("live_in", "prop", "person,place", "residence"),
    SeedEntry("work_at", "prop", "person,org", "workplace"),
    SeedEntry("study_at", "prop", "person,institution", "study place"),
]

_PROPS_EVENT = [
    SeedEntry("plan", "prop", "agent,content", "plan/intention content"),
    SeedEntry("event", "prop", "participant,description", "generic event"),
    SeedEntry("buy", "prop", "buyer,item", "purchase"),
    SeedEntry("visit", "prop", "visitor,destination", "visit/travel"),
    SeedEntry("meet", "prop", "person1,person2", "meeting"),
    SeedEntry("resign", "prop", "person", "resignation"),
    SeedEntry("marry", "prop", "person1,person2", "marriage"),
    SeedEntry("move", "prop", "person,destination", "relocation"),
    SeedEntry("start", "prop", "agent,activity", "starting something"),
    SeedEntry("stop", "prop", "agent,activity", "stopping something"),
    SeedEntry("birthday", "prop", "person", "birthday event"),
    SeedEntry("gift", "prop", "giver,recipient,item", "gift giving"),
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
    + _PROPS_RELATION
    + _PROPS_ATTRIBUTE
    + _PROPS_ACTION
    + _PROPS_EVENT
)

# Fast lookup: word → category
SEED_CATEGORY_MAP: Dict[str, str] = {e.word: e.category for e in SEED_VOCAB}

# Set of qualifier predicate names for quick checks
QUALIFIER_PREDICATES: set = {e.word for e in _QUALIFIERS}

# Set of correction-related predicates
CORRECTION_PREDICATES: set = {"correct_intent", "retract_intent"}
