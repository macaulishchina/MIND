from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from mind.config.schema import LLMConfig
from mind.llms.base import BaseLLM
from mind.prompts import (
    FACT_EXTRACTION_SYSTEM_PROMPT,
    UPDATE_DECISION_SYSTEM_PROMPT,
)


class FakeLLM(BaseLLM):
    """Deterministic LLM backend for tests.

    It implements the two prompts used by ``Memory.add()`` with simple,
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
    ) -> str:
        system_text = "\n".join(
            m.get("content", "") for m in messages if m.get("role") == "system"
        )
        user_text = "\n".join(
            m.get("content", "") for m in messages if m.get("role") == "user"
        )

        if FACT_EXTRACTION_SYSTEM_PROMPT in system_text:
            return self._extract_facts_response(user_text)
        if UPDATE_DECISION_SYSTEM_PROMPT in system_text:
            return self._decision_response(user_text)
        raise ValueError("FakeLLM received an unsupported prompt")

    def _extract_facts_response(self, prompt_text: str) -> str:
        conversation = prompt_text.split("Conversation:\n", 1)[-1]
        facts: List[Dict[str, Any]] = []
        for line in conversation.splitlines():
            if not line.startswith("User:"):
                continue
            content = line.split(":", 1)[1].strip()
            if not content or _looks_hypothetical(content):
                continue
            facts.append({"text": _clean_fact_text(content), "confidence": 0.9})
        return json.dumps({"facts": facts})

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
    return lowered.startswith("if ") or lowered.startswith("假如")


def _clean_fact_text(text: str) -> str:
    return text.strip().rstrip(".?!")


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
