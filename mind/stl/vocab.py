"""Seed vocabulary for the Semantic Translation Layer (v2).

Contains 85 seed predicates grouped by semantic domain.
v2: no prop/frame/qualifier category distinction — all are unified STMT.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional, Set


class SeedEntry(NamedTuple):
    word: str
    domain: str              # semantic domain for prompt grouping
    arg_schema: Optional[str]
    definition: str


# ── Relationships (22) ───────────────────────────────────────────────

_RELATIONSHIPS = [
    SeedEntry("friend", "relationships", "person_a,person_b", "friendship"),
    SeedEntry("mother", "relationships", "child,parent", "mother relation"),
    SeedEntry("father", "relationships", "child,parent", "father relation"),
    SeedEntry("brother", "relationships", "person_a,person_b", "brother relation"),
    SeedEntry("sister", "relationships", "person_a,person_b", "sister relation"),
    SeedEntry("spouse", "relationships", "person_a,person_b", "spouse relation"),
    SeedEntry("partner", "relationships", "person_a,person_b", "partner relation"),
    SeedEntry("child", "relationships", "parent,child", "child relation"),
    SeedEntry("cousin", "relationships", "person_a,person_b", "cousin relation"),
    SeedEntry("coworker", "relationships", "person_a,person_b", "coworker relation"),
    SeedEntry("boss", "relationships", "employee,boss", "boss relation"),
    SeedEntry("mentor", "relationships", "mentee,mentor", "mentor relation"),
    SeedEntry("student", "relationships", "student,institution_or_teacher", "student relation"),
    SeedEntry("roommate", "relationships", "person_a,person_b", "roommate relation"),
    SeedEntry("neighbor", "relationships", "person_a,person_b", "neighbor relation"),
    SeedEntry("classmate", "relationships", "person_a,person_b", "classmate relation"),
    SeedEntry("teammate", "relationships", "person_a,person_b", "teammate relation"),
    SeedEntry("client", "relationships", "provider,client", "client relation"),
    SeedEntry("landlord", "relationships", "tenant,landlord", "landlord relation"),
    SeedEntry("doctor", "relationships", "patient,doctor", "doctor relation"),
    SeedEntry("pet", "relationships", "owner,pet", "pet ownership"),
    SeedEntry("alias", "relationships", "entity,alias_name", "alternate name"),
]

# ── Attributes & States (18) ────────────────────────────────────────

_ATTRIBUTES = [
    SeedEntry("name", "attributes", "entity,name_value", "name"),
    SeedEntry("age", "attributes", "entity,age_value", "age"),
    SeedEntry("occupation", "attributes", "entity,occupation_value", "occupation"),
    SeedEntry("location", "attributes", "entity_or_stmt,place_value", "location"),
    SeedEntry("workplace", "attributes", "entity,workplace_value", "workplace"),
    SeedEntry("education", "attributes", "entity,education_value", "education"),
    SeedEntry("nationality", "attributes", "entity,nationality_value", "nationality"),
    SeedEntry("like", "attributes", "experiencer,target", "preference"),
    SeedEntry("dislike", "attributes", "experiencer,target", "dislike"),
    SeedEntry("habit", "attributes", "entity,habit_desc", "habitual behavior"),
    SeedEntry("hobby", "attributes", "entity,hobby_desc", "hobby/interest"),
    SeedEntry("skill", "attributes", "entity,skill_desc", "skill/ability"),
    SeedEntry("own", "attributes", "owner,object", "ownership"),
    SeedEntry("use", "attributes", "user,object", "usage"),
    SeedEntry("speak", "attributes", "speaker,language", "language spoken"),
    SeedEntry("live_in", "attributes", "entity,place", "residence"),
    SeedEntry("work_at", "attributes", "entity,workplace", "work at"),
    SeedEntry("study_at", "attributes", "entity,institution", "study at"),
]

# ── Actions & Events (14) ───────────────────────────────────────────

_ACTIONS = [
    SeedEntry("eat", "actions", "eater,food", "eating"),
    SeedEntry("drink", "actions", "drinker,beverage", "drinking"),
    SeedEntry("plan", "actions", "agent,content", "plan/intention"),
    SeedEntry("buy", "actions", "buyer,object", "purchase"),
    SeedEntry("visit", "actions", "visitor,destination", "visit/travel"),
    SeedEntry("meet", "actions", "person_a,person_b", "meeting"),
    SeedEntry("resign", "actions", "agent", "resignation"),
    SeedEntry("marry", "actions", "person_a,person_b", "marriage"),
    SeedEntry("move", "actions", "agent,destination", "relocation"),
    SeedEntry("start", "actions", "agent,activity", "starting"),
    SeedEntry("stop", "actions", "agent,activity", "stopping"),
    SeedEntry("birthday", "actions", "entity", "birthday event"),
    SeedEntry("gift", "actions", "giver,receiver,object", "gift giving"),
    SeedEntry("event", "actions", "participant,event_desc", "generic event"),
]

# ── Attitudes & Speech (15) ─────────────────────────────────────────

_ATTITUDES = [
    SeedEntry("believe", "attitudes", "experiencer,content", "belief"),
    SeedEntry("doubt", "attitudes", "experiencer,content", "doubt"),
    SeedEntry("know", "attitudes", "experiencer,content", "knowledge"),
    SeedEntry("uncertain", "attitudes", "experiencer,content", "uncertainty"),
    SeedEntry("hope", "attitudes", "experiencer,content", "hope"),
    SeedEntry("want", "attitudes", "experiencer,content", "desire"),
    SeedEntry("intend", "attitudes", "experiencer,content", "intention"),
    SeedEntry("say", "attitudes", "speaker,content", "speech: report"),
    SeedEntry("recommend", "attitudes", "speaker,content", "speech: recommendation"),
    SeedEntry("ask", "attitudes", "speaker,content", "speech: question"),
    SeedEntry("promise", "attitudes", "speaker,content", "speech: promise"),
    SeedEntry("emotion", "attitudes", "experiencer,emotion_type", "emotional state"),
    SeedEntry("decide", "attitudes", "agent,content", "decision made"),
    SeedEntry("defer", "attitudes", "agent,content", "decision deferred"),
    SeedEntry("undecided", "attitudes", "agent,content", "decision pending"),
]

# ── Logic & Modality (11) ───────────────────────────────────────────

_LOGIC = [
    SeedEntry("neg", "logic", "content", "negation"),
    SeedEntry("if", "logic", "condition,consequence", "conditional"),
    SeedEntry("cause", "logic", "cause,effect", "causal (cause→effect)"),
    SeedEntry("because", "logic", "effect,cause", "causal (effect←cause)"),
    SeedEntry("must", "logic", "obligee,content", "obligation"),
    SeedEntry("permit", "logic", "authority,content", "permission"),
    SeedEntry("should", "logic", "obligee,content", "suggestion"),
    SeedEntry("lie", "logic", "speaker,content", "false narrative"),
    SeedEntry("joke", "logic", "speaker,content", "humorous/non-serious"),
    SeedEntry("retract_intent", "logic", "speaker,content_desc", "retraction intent"),
    SeedEntry("correct_intent", "logic", "speaker,content", "correction intent"),
]

# ── Modifiers (5) ───────────────────────────────────────────────────
# First arg must be $id (the modified STMT).

_MODIFIERS = [
    SeedEntry("time", "modifiers", "target,time_value", "temporal anchor"),
    SeedEntry("degree", "modifiers", "target,degree_value", "degree modifier"),
    SeedEntry("quantity", "modifiers", "target,quantity_value", "quantity modifier"),
    SeedEntry("frequency", "modifiers", "target,freq_value", "frequency modifier"),
    SeedEntry("duration", "modifiers", "target,duration_value", "duration modifier"),
]

# ── Aggregate ────────────────────────────────────────────────────────

SEED_VOCAB: List[SeedEntry] = (
    _RELATIONSHIPS
    + _ATTRIBUTES
    + _ACTIONS
    + _ATTITUDES
    + _LOGIC
    + _MODIFIERS
)

# Fast lookup: word → domain
SEED_DOMAIN_MAP: Dict[str, str] = {e.word: e.domain for e in SEED_VOCAB}

# All seed words as a set (for validation)
SEED_WORDS: Set[str] = set(SEED_DOMAIN_MAP.keys())

# Set of modifier predicate names for quick checks
MODIFIER_PREDICATES: Set[str] = {e.word for e in _MODIFIERS}

# Set of correction-related predicates
CORRECTION_PREDICATES: Set[str] = {"correct_intent", "retract_intent"}
