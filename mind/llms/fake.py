from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from mind.config.schema import LLMConfig
from mind.llms.base import BaseLLM
from mind.prompts import (
    FACT_EXTRACTION_SYSTEM_PROMPT,
    FACT_NORMALIZATION_SYSTEM_PROMPT,
    UPDATE_DECISION_SYSTEM_PROMPT,
)
from mind.stl.prompt import STL_EXTRACTION_SYSTEM_PROMPT


class FakeLLM(BaseLLM):
    """Deterministic LLM backend for tests.

    It implements the prompts used by ``Memory.add()`` with simple,
    explicit heuristics so tests can exercise the full memory pipeline
    without external API calls.
    """

    provider = "fake"
    model = "fake-memory-test"

    def __init__(self, config: LLMConfig, **kwargs) -> None:
        self.config = config
        self.model = config.model or self.model

    def _generate(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict[str, Any]] = None,
        temperature: Optional[float] = None,
    ) -> str:
        system_text = "\n".join(
            m.get("content", "") for m in messages if m.get("role") == "system"
        )
        user_text = "\n".join(
            m.get("content", "") for m in messages if m.get("role") == "user"
        )

        if FACT_EXTRACTION_SYSTEM_PROMPT in system_text:
            return self._extract_facts_response(user_text)
        if FACT_NORMALIZATION_SYSTEM_PROMPT in system_text:
            return self._normalize_fact_response(user_text)
        if UPDATE_DECISION_SYSTEM_PROMPT in system_text:
            return self._decision_response(user_text)
        if STL_EXTRACTION_SYSTEM_PROMPT in system_text:
            return self._extract_stl_response(user_text)
        raise ValueError("FakeLLM received an unsupported prompt")

    def _extract_facts_response(self, prompt_text: str) -> str:
        conversation = prompt_text.split("Conversation:\n", 1)[-1]
        facts: List[Dict[str, Any]] = []
        for line in conversation.splitlines():
            if not line.startswith("User:"):
                continue
            content = line.split(":", 1)[1].strip()
            if (
                not content
                or _looks_hypothetical(content)
                or _looks_like_question(content)
            ):
                continue
            for clause in _split_into_fact_candidates(content):
                cleaned = _clean_fact_text(clause)
                if not cleaned or _is_low_value_clause(cleaned):
                    continue
                facts.append(
                    {
                        "text": cleaned,
                        "confidence": _estimate_confidence(cleaned),
                    }
                )
        return json.dumps({"facts": facts})

    def _normalize_fact_response(self, prompt_text: str) -> str:
        raw_fact = prompt_text.split("Raw fact:\n", 1)[-1].strip()
        envelopes = _normalize_raw_fact(raw_fact)
        return json.dumps({"envelopes": envelopes})

    def _decision_response(self, prompt_text: str) -> str:
        existing_memories = _parse_existing_memories(prompt_text)
        new_fact = _parse_new_fact(prompt_text)
        if not new_fact:
            return json.dumps(
                {"action": "NONE", "id": None, "text": "", "reason": "empty fact"}
            )

        if not existing_memories:
            return json.dumps(
                {
                    "action": "ADD",
                    "id": None,
                    "text": new_fact,
                    "reason": "new information",
                }
            )

        new_norm = _normalize_text(new_fact)
        best_id: Optional[str] = None
        best_score = 0
        best_text = ""

        for temp_id, existing_text in existing_memories:
            existing_norm = _normalize_text(existing_text)
            if new_norm == existing_norm:
                return json.dumps(
                    {
                        "action": "NONE",
                        "id": temp_id,
                        "text": existing_text,
                        "reason": "already captured",
                    }
                )

            score = len(_topic_tokens(new_fact) & _topic_tokens(existing_text))
            if score > best_score:
                best_score = score
                best_id = temp_id
                best_text = existing_text

        if best_id is None or best_score == 0:
            return json.dumps(
                {
                    "action": "ADD",
                    "id": None,
                    "text": new_fact,
                    "reason": "distinct topic",
                }
            )

        return json.dumps(
            {
                "action": "UPDATE",
                "id": best_id,
                "text": _merge_memory_text(best_text, new_fact),
                "reason": "same topic with newer or better detail",
            }
        )

    def _extract_stl_response(self, prompt_text: str) -> str:
        conversation = prompt_text.split("Conversation:\n", 1)[-1]
        builder = _FakeSTLBuilder()

        for turn_index, line in enumerate(conversation.splitlines(), start=1):
            if not line.startswith("User:"):
                continue
            content = line.split(":", 1)[1].strip()
            if not content or _looks_like_question(content):
                continue

            if _handle_frame_patterns(builder, content, turn_index):
                continue
            if _handle_relation_patterns(builder, content, turn_index):
                continue

            for clause in _split_into_fact_candidates(content):
                _handle_self_clause(builder, clause, turn_index)

        return builder.render()


class _FakeSTLBuilder:
    """Small helper for deterministic STL emission in tests."""

    def __init__(self) -> None:
        self.lines: List[str] = []
        self._declared_self = False
        self._declared_refs: Dict[str, str] = {}
        self._prop_count = 0
        self._frame_count = 0
        self._blank_count = 0

    def _ensure_self(self) -> str:
        if not self._declared_self:
            self.lines.append("@s = @self")
            self._declared_self = True
        return "@s"

    def local_person(self, name: str) -> str:
        key = _normalize_entity_key(name)
        alias = self._declared_refs.get(f"person:{key}")
        if alias:
            return alias

        alias = f"@p{len(self._declared_refs) + 1}"
        self.lines.append(f'{alias} = @local/person("{key}")')
        self._declared_refs[f"person:{key}"] = alias
        return alias

    def world_entity(self, ref_type: str, key: str) -> str:
        norm_key = _normalize_entity_key(key)
        cache_key = f"{ref_type}:{norm_key}"
        alias = self._declared_refs.get(cache_key)
        if alias:
            return alias

        alias = f"@w{len(self._declared_refs) + 1}"
        self.lines.append(f'{alias} = @world/{ref_type}("{norm_key}")')
        self._declared_refs[cache_key] = alias
        return alias

    def blank_ref(self) -> str:
        self._blank_count += 1
        alias = f"@u{self._blank_count}"
        self.lines.append(f"{alias} = _:u{self._blank_count}")
        return alias

    def prop(
        self,
        predicate: str,
        args: List[str],
        turn_index: int,
        conf: float = 0.9,
        span: Optional[str] = None,
        frame: bool = False,
    ) -> str:
        counter_attr = "_frame_count" if frame else "_prop_count"
        setattr(self, counter_attr, getattr(self, counter_attr) + 1)
        prefix = "f" if frame else "p"
        local_id = f"{prefix}{getattr(self, counter_attr)}"
        self.lines.append(f"${local_id} = {predicate}({', '.join(args)})")
        ev = f'ev(${local_id}, conf={conf:.1f}, src="turn_{turn_index}")'
        if span:
            ev = ev[:-1] + f', span="{span}")'
        self.lines.append(ev)
        return f"${local_id}"

    def render(self) -> str:
        return "\n".join(self.lines).strip()


def _handle_self_clause(builder: _FakeSTLBuilder, clause: str, turn_index: int) -> bool:
    cleaned = _clean_fact_text(clause)
    if not cleaned:
        return False

    builder._ensure_self()

    patterns = (
        (r"^(?:my name is|i am|i'm)\s+([A-Za-z][A-Za-z0-9 _'-]*)$", "name", lambda m: f'"{m.group(1).strip()}"'),
        (r"^(?:i am|i'm)\s+(\d{1,3})\s+years?\s+old$", "age", lambda m: m.group(1)),
        (r"^(?:i work at|i work for)\s+(.+)$", "work_at", lambda m: f'"{m.group(1).strip()}"'),
        (r"^(?:i live in|i currently live in)\s+(.+)$", "live_in", lambda m: f'"{m.group(1).strip()}"'),
        (r"^(?:i love|i like|i enjoy)\s+(.+)$", "like", lambda m: f'"{m.group(1).strip()}"'),
        (r"^(?:i drink)\s+(.+)$", "drink", lambda m: f'"{m.group(1).strip()}"'),
    )
    for pattern, predicate, value_fn in patterns:
        match = re.match(pattern, cleaned, re.I)
        if match:
            builder.prop(predicate, ["@s", value_fn(match)], turn_index)
            return True

    zh_patterns = (
        (r"^我叫(.+)$", "name", lambda m: f'"{m.group(1).strip()}"'),
        (r"^我在(.+)工作$", "work_at", lambda m: f'"{m.group(1).strip()}"'),
        (r"^我住在(.+)$", "live_in", lambda m: f'"{m.group(1).strip()}"'),
        (r"^我喜欢(.+)$", "like", lambda m: f'"{m.group(1).strip()}"'),
    )
    for pattern, predicate, value_fn in zh_patterns:
        match = re.match(pattern, cleaned)
        if match:
            builder.prop(predicate, ["@s", value_fn(match)], turn_index)
            return True

    return False


def _handle_relation_patterns(builder: _FakeSTLBuilder, text: str, turn_index: int) -> bool:
    cleaned = _clean_fact_text(text)
    if not cleaned:
        return False

    builder._ensure_self()

    named_is = re.match(
        r"^My\s+(friend|coworker|boss|mother|father|brother|sister|mentor|roommate|neighbor)\s+([A-Z][A-Za-z0-9_-]*)\s+is\s+(?:a\s+|an\s+)?(.+)$",
        cleaned,
        re.I,
    )
    if named_is:
        relation = _normalize_relation_name(named_is.group(1))
        person_ref = builder.local_person(named_is.group(2))
        builder.prop(relation, ["@s", person_ref], turn_index)
        builder.prop("occupation", [person_ref, f'"{named_is.group(3).strip()}"'], turn_index)
        return True

    named_drink = re.match(
        r"^My\s+(friend|coworker|boss|mother|father|brother|sister|mentor|roommate|neighbor)\s+([A-Z][A-Za-z0-9_-]*)\s+drinks\s+(.+)$",
        cleaned,
        re.I,
    )
    if named_drink:
        relation = _normalize_relation_name(named_drink.group(1))
        person_ref = builder.local_person(named_drink.group(2))
        builder.prop(relation, ["@s", person_ref], turn_index)
        builder.prop("drink", [person_ref, f'"{named_drink.group(3).strip()}"'], turn_index)
        return True

    named_like = re.match(
        r"^My\s+(friend|coworker|boss|mother|father|brother|sister|mentor|roommate|neighbor)\s+([A-Z][A-Za-z0-9_-]*)\s+likes\s+(.+)$",
        cleaned,
        re.I,
    )
    if named_like:
        relation = _normalize_relation_name(named_like.group(1))
        person_ref = builder.local_person(named_like.group(2))
        builder.prop(relation, ["@s", person_ref], turn_index)
        builder.prop("like", [person_ref, f'"{named_like.group(3).strip()}"'], turn_index)
        return True

    named_live_in = re.match(
        r"^My\s+(friend|coworker|boss|mother|father|brother|sister|mentor|roommate|neighbor)\s+([A-Z][A-Za-z0-9_-]*)\s+lives\s+in\s+(.+)$",
        cleaned,
        re.I,
    )
    if named_live_in:
        relation = _normalize_relation_name(named_live_in.group(1))
        person_ref = builder.local_person(named_live_in.group(2))
        builder.prop(relation, ["@s", person_ref], turn_index)
        builder.prop("live_in", [person_ref, f'"{named_live_in.group(3).strip()}"'], turn_index)
        return True

    unknown_attr = re.match(
        r"^I have a\s+(friend|coworker|boss|neighbor)\s+who is\s+(.+)$",
        cleaned,
        re.I,
    )
    if unknown_attr:
        relation = _normalize_relation_name(unknown_attr.group(1))
        person_ref = builder.blank_ref()
        builder.prop(relation, ["@s", person_ref], turn_index)
        builder.prop("attribute", [person_ref, f'"{unknown_attr.group(2).strip()}"'], turn_index)
        return True

    inverse_like = re.match(
        r"^([A-Z][A-Za-z0-9_-]*)\s+is\s+my\s+(friend|coworker|boss|mother|father|mentor|roommate|neighbor)\s+and\s+(?:he|she)\s+likes\s+(.+)$",
        cleaned,
        re.I,
    )
    if inverse_like:
        relation = _normalize_relation_name(inverse_like.group(2))
        person_ref = builder.local_person(inverse_like.group(1))
        builder.prop(relation, ["@s", person_ref], turn_index)
        builder.prop("like", [person_ref, f'"{inverse_like.group(3).strip()}"'], turn_index)
        return True

    return False


def _handle_frame_patterns(builder: _FakeSTLBuilder, text: str, turn_index: int) -> bool:
    cleaned = _clean_fact_text(text)
    if not cleaned:
        return False

    builder._ensure_self()

    hope_match = re.match(
        r"^I hope\s+([A-Z][A-Za-z0-9_-]*)\s+comes?\s+to\s+([A-Z][A-Za-z0-9_-]*)$",
        cleaned,
        re.I,
    )
    if hope_match:
        person_ref = builder.local_person(hope_match.group(1))
        city_ref = builder.world_entity("city", hope_match.group(2))
        target = builder.prop("come", [person_ref, city_ref], turn_index)
        builder.prop("hope", ["@s", target], turn_index, frame=True)
        return True

    say_match = re.match(
        r"^([A-Z][A-Za-z0-9_-]*)\s+says\s+([A-Z][A-Za-z0-9_-]*)\s+lives?\s+in\s+([A-Z][A-Za-z0-9_-]*)$",
        cleaned,
        re.I,
    )
    if say_match:
        speaker_ref = builder.local_person(say_match.group(1))
        person_ref = builder.local_person(say_match.group(2))
        city_ref = builder.world_entity("city", say_match.group(3))
        target = builder.prop("live_in", [person_ref, city_ref], turn_index)
        builder.prop("say", [speaker_ref, target], turn_index, conf=0.8, frame=True)
        return True

    believe_match = re.match(
        r"^I think my (mom|mother|dad|father)\s+likes\s+(.+)$",
        cleaned,
        re.I,
    )
    if believe_match:
        relation = _normalize_relation_name(believe_match.group(1))
        person_ref = builder.local_person("mom" if relation == "mother" else "dad")
        builder.prop(relation, ["@s", person_ref], turn_index)
        target = builder.prop("like", [person_ref, f'"{believe_match.group(2).strip()}"'], turn_index)
        builder.prop("believe", ["@s", target], turn_index, conf=0.6, frame=True)
        return True

    if_match = re.match(
        r"^If it rains tomorrow,\s+I will\s+(.+)$",
        cleaned,
        re.I,
    )
    if if_match:
        target = builder.prop("plan", ["@s", f'"{if_match.group(1).strip()}"'], turn_index)
        builder.prop("if", ['rain("tomorrow")', target], turn_index, frame=True)
        return True

    return False


def _normalize_relation_name(raw_relation: str) -> str:
    relation = raw_relation.strip().casefold().replace(" ", "_")
    relation_map = {
        "mom": "mother",
        "dad": "father",
        "sister": "sibling",
        "brother": "sibling",
        "colleague": "coworker",
    }
    return relation_map.get(relation, relation)


def _normalize_entity_key(raw_key: str) -> str:
    return _clean_fact_text(raw_key).strip().casefold().replace(" ", "_")


def _parse_existing_memories(prompt_text: str) -> List[tuple[str, str]]:
    memories: List[tuple[str, str]] = []
    in_section = False
    for line in prompt_text.splitlines():
        if line.startswith("Existing memories:"):
            in_section = True
            continue
        if line.startswith("New fact:"):
            break
        if not in_section:
            continue

        match = re.match(r"\[(\d+)\]\s+(.*)", line.strip())
        if match:
            memories.append((match.group(1), match.group(2).strip()))
    return memories


def _parse_new_fact(prompt_text: str) -> str:
    match = re.search(r"New fact:\s*(.*?)\n\nDecide what action to take\.", prompt_text, re.S)
    if not match:
        return ""
    return match.group(1).strip()


def _looks_hypothetical(text: str) -> bool:
    lowered = text.lower()
    return (
        lowered.startswith("if ")
        or lowered.startswith("假如")
        or lowered.startswith("如果")
        or " might " in lowered
        or " maybe " in lowered
        or "可能" in text
    )


def _looks_like_question(text: str) -> bool:
    stripped = text.strip()
    lowered = stripped.lower()
    question_starters = (
        "do you",
        "can you",
        "could you",
        "would you",
        "what",
        "why",
        "how",
        "should i",
        "你觉得",
        "请问",
        "可以",
        "能不能",
        "要不要",
    )
    return stripped.endswith(("?", "？")) or lowered.startswith(question_starters)


def _split_into_fact_candidates(text: str) -> List[str]:
    normalized = text.replace("，", ", ").replace("；", "; ")
    pieces = [normalized]
    delimiters = [r"\s*,\s*", r"\s*;\s*", r"\s+and\s+", r"\s+but\s+"]
    for delimiter in delimiters:
        next_pieces: List[str] = []
        for piece in pieces:
            next_pieces.extend(part for part in re.split(delimiter, piece) if part)
        pieces = next_pieces

    expanded: List[str] = []
    for piece in pieces:
        expanded.extend(_split_chinese_transitions(piece))

    return [piece.strip() for piece in expanded if piece.strip()]


def _split_chinese_transitions(text: str) -> List[str]:
    transition_markers = ["现在", "后来", "目前"]
    for marker in transition_markers:
        marker_index = text.find(marker)
        if marker_index > 0:
            before = text[:marker_index].rstrip(" ,")
            after = text[marker_index:].lstrip(" ,")
            return [part for part in [before, after] if part]
    return [text]


def _is_low_value_clause(text: str) -> bool:
    lowered = text.lower()
    low_value_markers = (
        "noted",
        "thanks",
        "thank you",
        "ok",
        "okay",
        "nice progress",
        "收到",
        "好的",
        "谢谢",
    )
    if any(marker == lowered for marker in low_value_markers):
        return True
    return len(text) <= 1


def _estimate_confidence(text: str) -> float:
    if any(marker in text for marker in ["started", "last month", "上周", "上个月", "最近"]):
        return 0.8
    return 0.9


def _clean_fact_text(text: str) -> str:
    return text.strip().rstrip(".?!。！？")


def _normalize_raw_fact(text: str) -> List[Dict[str, Any]]:
    cleaned = _clean_fact_text(text)
    if not cleaned:
        return []

    handlers = (
        _normalize_self_name,
        _normalize_self_age,
        _normalize_self_location,
        _normalize_self_workplace,
        _normalize_third_party_fact,
        _normalize_self_preference_or_habit,
    )
    for handler in handlers:
        normalized = handler(cleaned)
        if normalized:
            return normalized

    return [
        {
            "subject_scope": "self",
            "relation_type": "self",
            "display_name": None,
            "normalized_name": None,
            "fact_family": "attribute",
            "field_key": "attribute:statement",
            "field_value_json": {"value": cleaned},
            "confidence": _estimate_confidence(cleaned),
        }
    ]


def _normalize_self_name(text: str) -> List[Dict[str, Any]]:
    patterns = (
        r"^(?:my name is|i am|i'm)\s+([A-Za-z][A-Za-z0-9 _'-]*)$",
        r"^user'?s name is\s+([A-Za-z][A-Za-z0-9 _'-]*)$",
    )
    for pattern in patterns:
        match = re.match(pattern, text, re.I)
        if match:
            return [_envelope("self", "self", "attribute", "name", match.group(1).strip(), text)]
    return []


def _normalize_self_age(text: str) -> List[Dict[str, Any]]:
    patterns = (
        r"^(?:i am|i'm)\s+(\d{1,3})\s+years?\s+old$",
        r"^user is\s+(\d{1,3})\s+years?\s+old$",
    )
    for pattern in patterns:
        match = re.match(pattern, text, re.I)
        if match:
            return [_envelope("self", "self", "attribute", "age", int(match.group(1)), text)]
    return []


def _normalize_self_location(text: str) -> List[Dict[str, Any]]:
    patterns = (
        r"^(?:i live in|i currently live in)\s+(.+)$",
        r"^user (?:currently )?lives in\s+(.+)$",
    )
    for pattern in patterns:
        match = re.match(pattern, text, re.I)
        if match:
            return [_envelope("self", "self", "attribute", "location", match.group(1).strip(), text)]
    return []


def _normalize_self_workplace(text: str) -> List[Dict[str, Any]]:
    patterns = (
        r"^(?:i work at|i work for)\s+(.+)$",
        r"^user works (?:at|for)\s+(.+)$",
    )
    for pattern in patterns:
        match = re.match(pattern, text, re.I)
        if match:
            return [_envelope("self", "self", "attribute", "workplace", match.group(1).strip(), text)]
    return []


def _normalize_self_preference_or_habit(text: str) -> List[Dict[str, Any]]:
    lowered = text.lower()
    if lowered.startswith(("i like ", "i love ", "user likes ", "user loves ")):
        value = re.sub(r"^(?:i|user)\s+(?:like|likes|love|loves)\s+", "", text, flags=re.I)
        return [_envelope("self", "self", "preference", "preference:general", value.strip(), text)]
    if lowered.startswith(("i enjoy ", "user enjoys ")):
        value = re.sub(r"^(?:i|user)\s+(?:enjoy|enjoys)\s+", "", text, flags=re.I)
        return [_envelope("self", "self", "habit", "habit:activity", value.strip(), text)]
    if "usually uses" in lowered or "usually communicates in" in lowered:
        value = re.sub(r"^user\s+(?:usually uses|usually communicates in)\s+", "", text, flags=re.I)
        return [_envelope("self", "self", "habit", "habit:language", value.strip(), text)]
    return []


def _normalize_third_party_fact(text: str) -> List[Dict[str, Any]]:
    relation_map = {
        "friend": "friend",
        "mother": "mother",
        "mom": "mother",
        "father": "father",
        "dad": "father",
        "boss": "boss",
        "manager": "manager",
        "roommate": "roommate",
        "partner": "partner",
        "wife": "partner",
        "husband": "partner",
        "girlfriend": "partner",
        "boyfriend": "partner",
        "coworker": "coworker",
        "colleague": "coworker",
        "brother": "sibling",
        "sister": "sibling",
        "son": "child",
        "daughter": "child",
        "dog": "pet",
        "cat": "pet",
        "pet": "pet",
    }
    relation_pattern = "|".join(sorted(relation_map, key=len, reverse=True))

    named_patterns = (
        rf"^(?:my|user'?s)\s+({relation_pattern})\s+([A-Za-z][A-Za-z0-9 _'-]*)\s+is\s+(.+)$",
        rf"^([A-Za-z][A-Za-z0-9 _'-]*)\s+is\s+my\s+({relation_pattern})$",
    )
    for pattern in named_patterns:
        match = re.match(pattern, text, re.I)
        if not match:
            continue

        if len(match.groups()) == 3:
            raw_relation, display_name, predicate = match.groups()
        else:
            display_name, raw_relation = match.groups()
            predicate = None

        relation_type = relation_map[raw_relation.lower()]
        envelopes = [
            _envelope(
                "third_party_named",
                relation_type,
                "relation",
                "relation_to_owner",
                relation_type,
                text,
                display_name=display_name.strip(),
            )
        ]
        if predicate:
            attribute_key, attribute_value = _infer_attribute_from_predicate(predicate.strip())
            envelopes.append(
                _envelope(
                    "third_party_named",
                    relation_type,
                    "attribute",
                    attribute_key,
                    attribute_value,
                    text,
                    display_name=display_name.strip(),
                )
            )
        return envelopes

    unknown_pattern = rf"^(?:i have|i've got|my)\s+(?:a\s+|an\s+)?({relation_pattern})(?:\s+who)?\s+is\s+(.+)$"
    match = re.match(unknown_pattern, text, re.I)
    if match:
        raw_relation, predicate = match.groups()
        relation_type = relation_map[raw_relation.lower()]
        attribute_key, attribute_value = _infer_attribute_from_predicate(predicate.strip())
        return [
            _envelope(
                "third_party_unknown",
                relation_type,
                "relation",
                "relation_to_owner",
                relation_type,
                text,
            ),
            _envelope(
                "third_party_unknown",
                relation_type,
                "attribute",
                attribute_key,
                attribute_value,
                text,
            ),
        ]

    return []


def _infer_attribute_from_predicate(predicate: str) -> tuple[str, Any]:
    lowered = predicate.lower()
    if re.fullmatch(r"\d{1,3}\s+years?\s+old", lowered):
        return "age", int(re.findall(r"\d+", lowered)[0])
    if any(marker in lowered for marker in ("football player", "soccer player", "engineer", "teacher", "doctor", "developer", "designer")):
        cleaned = re.sub(r"^(?:a|an)\s+", "", predicate, flags=re.I)
        return "occupation", cleaned
    if lowered.startswith(("named ", "called ")):
        return "name", predicate.split(" ", 1)[1].strip()
    return "attribute:statement", predicate


def _envelope(
    subject_scope: str,
    relation_type: str,
    fact_family: str,
    field_key: str,
    value: Any,
    raw_text: str,
    display_name: Optional[str] = None,
) -> Dict[str, Any]:
    normalized_name = _normalize_name(display_name) if display_name else None
    return {
        "subject_scope": subject_scope,
        "relation_type": relation_type,
        "display_name": display_name,
        "normalized_name": normalized_name,
        "fact_family": fact_family,
        "field_key": field_key,
        "field_value_json": {"value": value},
        "confidence": _estimate_confidence(raw_text),
    }


def _normalize_name(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return " ".join(value.casefold().split())


def _normalize_text(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _topic_tokens(text: str) -> set[str]:
    lowered = text.lower()
    tokens = set(re.findall(r"[a-z]+", lowered))

    concepts = {
        "beverage": {"coffee", "americano", "drink", "drinks", "tea", "beverage"},
        "allergy": {"allergic", "allergy", "allergies", "peanut", "peanuts", "food"},
        "identity": {"name", "call", "called", "dave", "david"},
        "work": {"work", "startup", "engineer", "manager", "job", "company", "tech"},
        "hobby": {"hiking", "hike", "hobby"},
    }
    for concept, keywords in concepts.items():
        if any(keyword in tokens for keyword in keywords):
            tokens.add(concept)
    return tokens


def _merge_memory_text(existing_text: str, new_fact: str) -> str:
    existing_tokens = _topic_tokens(existing_text)
    new_tokens = _topic_tokens(new_fact)
    if existing_tokens == new_tokens:
        return new_fact
    return new_fact
