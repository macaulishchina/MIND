from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from mind.config.schema import LLMConfig
from mind.llms.base import BaseLLM
from mind.prompts import UPDATE_DECISION_SYSTEM_PROMPT
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

        if UPDATE_DECISION_SYSTEM_PROMPT in system_text:
            return self._decision_response(user_text)
        if STL_EXTRACTION_SYSTEM_PROMPT in system_text:
            return self._extract_stl_response(user_text)
        return self._generic_response(user_text)

    @staticmethod
    def _generic_response(prompt_text: str) -> str:
        text = prompt_text.strip()
        if not text:
            return "hello"
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return "hello"
        return f"echo: {lines[-1][:80]}"

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

        for line in conversation.splitlines():
            if not line.startswith("User:"):
                continue
            content = line.split(":", 1)[1].strip()
            if not content or _looks_like_question(content):
                continue

            if _handle_frame_patterns(builder, content):
                continue
            if _handle_relation_patterns(builder, content):
                continue

            for clause in _split_into_fact_candidates(content):
                _handle_self_clause(builder, clause)

        return builder.render()


class _FakeSTLBuilder:
    """Small helper for deterministic STL emission in tests."""

    def __init__(self) -> None:
        self.lines: List[str] = []
        self._declared_refs: Dict[str, str] = {}
        self._prop_count = 0
        self._frame_count = 0
        self._blank_count = 0

    def _ensure_self(self) -> str:
        return "@self"

    def local_person(self, name: str) -> str:
        key = _normalize_entity_key(name)
        alias = self._declared_refs.get(f"person:{key}")
        if alias:
            return alias

        alias = f"@p{len(self._declared_refs) + 1}"
        self.lines.append(f'{alias}: person "{key}"')
        self._declared_refs[f"person:{key}"] = alias
        return alias

    def world_entity(self, ref_type: str, key: str) -> str:
        norm_key = _normalize_entity_key(key)
        cache_key = f"{ref_type}:{norm_key}"
        alias = self._declared_refs.get(cache_key)
        if alias:
            return alias

        alias = f"@w{len(self._declared_refs) + 1}"
        self.lines.append(f'{alias}: {ref_type} "{norm_key}"')
        self._declared_refs[cache_key] = alias
        return alias

    def blank_ref(self) -> str:
        self._blank_count += 1
        alias = f"@u{self._blank_count}"
        self.lines.append(f"{alias}: entity")
        return alias

    def prop(
        self,
        predicate: str,
        args: List[str],
        conf: float = 0.9,
        span: Optional[str] = None,
        frame: bool = False,
    ) -> str:
        counter_attr = "_frame_count" if frame else "_prop_count"
        setattr(self, counter_attr, getattr(self, counter_attr) + 1)
        prefix = "f" if frame else "p"
        local_id = f"{prefix}{getattr(self, counter_attr)}"
        self.lines.append(f"${local_id} = {predicate}({', '.join(args)})")
        return f"${local_id}"

    def render(self) -> str:
        return "\n".join(self.lines).strip()


def _handle_self_clause(builder: _FakeSTLBuilder, clause: str) -> bool:
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
            builder.prop(predicate, ["@self", value_fn(match)])
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
            builder.prop(predicate, ["@self", value_fn(match)])
            return True

    return False


def _handle_relation_patterns(builder: _FakeSTLBuilder, text: str) -> bool:
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
        builder.prop(relation, ["@self", person_ref])
        builder.prop("occupation", [person_ref, f'"{named_is.group(3).strip()}"'])
        return True

    named_drink = re.match(
        r"^My\s+(friend|coworker|boss|mother|father|brother|sister|mentor|roommate|neighbor)\s+([A-Z][A-Za-z0-9_-]*)\s+drinks\s+(.+)$",
        cleaned,
        re.I,
    )
    if named_drink:
        relation = _normalize_relation_name(named_drink.group(1))
        person_ref = builder.local_person(named_drink.group(2))
        builder.prop(relation, ["@self", person_ref])
        builder.prop("drink", [person_ref, f'"{named_drink.group(3).strip()}"'])
        return True

    named_like = re.match(
        r"^My\s+(friend|coworker|boss|mother|father|brother|sister|mentor|roommate|neighbor)\s+([A-Z][A-Za-z0-9_-]*)\s+likes\s+(.+)$",
        cleaned,
        re.I,
    )
    if named_like:
        relation = _normalize_relation_name(named_like.group(1))
        person_ref = builder.local_person(named_like.group(2))
        builder.prop(relation, ["@self", person_ref])
        builder.prop("like", [person_ref, f'"{named_like.group(3).strip()}"'])
        return True

    named_live_in = re.match(
        r"^My\s+(friend|coworker|boss|mother|father|brother|sister|mentor|roommate|neighbor)\s+([A-Z][A-Za-z0-9_-]*)\s+lives\s+in\s+(.+)$",
        cleaned,
        re.I,
    )
    if named_live_in:
        relation = _normalize_relation_name(named_live_in.group(1))
        person_ref = builder.local_person(named_live_in.group(2))
        builder.prop(relation, ["@self", person_ref])
        builder.prop("live_in", [person_ref, f'"{named_live_in.group(3).strip()}"'])
        return True

    unknown_attr = re.match(
        r"^I have a\s+(friend|coworker|boss|neighbor)\s+who is\s+(.+)$",
        cleaned,
        re.I,
    )
    if unknown_attr:
        relation = _normalize_relation_name(unknown_attr.group(1))
        person_ref = builder.blank_ref()
        builder.prop(relation, ["@self", person_ref])
        builder.prop("attribute", [person_ref, f'"{unknown_attr.group(2).strip()}"'])
        return True

    inverse_like = re.match(
        r"^([A-Z][A-Za-z0-9_-]*)\s+is\s+my\s+(friend|coworker|boss|mother|father|mentor|roommate|neighbor)\s+and\s+(?:he|she)\s+likes\s+(.+)$",
        cleaned,
        re.I,
    )
    if inverse_like:
        relation = _normalize_relation_name(inverse_like.group(2))
        person_ref = builder.local_person(inverse_like.group(1))
        builder.prop(relation, ["@self", person_ref])
        builder.prop("like", [person_ref, f'"{inverse_like.group(3).strip()}"'])
        return True

    return False


def _handle_frame_patterns(builder: _FakeSTLBuilder, text: str) -> bool:
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
        target = builder.prop("come", [person_ref, city_ref])
        builder.prop("hope", ["@self", target], frame=True)
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
        target = builder.prop("live_in", [person_ref, city_ref])
        builder.prop("say", [speaker_ref, target], conf=0.8, frame=True)
        return True

    believe_match = re.match(
        r"^I think my (mom|mother|dad|father)\s+likes\s+(.+)$",
        cleaned,
        re.I,
    )
    if believe_match:
        relation = _normalize_relation_name(believe_match.group(1))
        person_ref = builder.local_person("mom" if relation == "mother" else "dad")
        builder.prop(relation, ["@self", person_ref])
        target = builder.prop("like", [person_ref, f'"{believe_match.group(2).strip()}"'])
        builder.prop("believe", ["@self", target], conf=0.6, frame=True)
        return True

    if_match = re.match(
        r"^If it rains tomorrow,\s+I will\s+(.+)$",
        cleaned,
        re.I,
    )
    if if_match:
        target = builder.prop("plan", ["@self", f'"{if_match.group(1).strip()}"'])
        cond = builder.prop("neg", ['"rain_tomorrow"'])
        builder.prop("if", [cond, target], frame=True)
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


def _clean_fact_text(text: str) -> str:
    return text.strip().rstrip(".?!。！？")


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
