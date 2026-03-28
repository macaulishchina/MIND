from __future__ import annotations

import hashlib
import math
import re
from typing import List

from mind.config.schema import EmbeddingConfig
from mind.embeddings.base import BaseEmbedding


class FakeEmbedding(BaseEmbedding):
    """Deterministic embedding backend for tests."""

    def __init__(self, config: EmbeddingConfig, **kwargs) -> None:
        self.config = config

    def _embed(self, text: str) -> List[float]:
        dimensions = self.config.dimensions
        vector = [0.0] * dimensions

        for token in _expanded_tokens(text):
            digest = hashlib.md5(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % dimensions
            weight = 2.0 if token.startswith("concept:") else 1.0
            vector[index] += weight

        if not any(vector):
            vector[0] = 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector]


def _expanded_tokens(text: str) -> List[str]:
    lowered = text.lower()
    tokens = re.findall(r"[a-z]+", lowered)
    expanded = list(tokens)

    concepts = {
        "beverage": {"coffee", "americano", "drink", "drinks", "tea", "beverage", "recommend"},
        "allergy": {"allergic", "allergy", "allergies", "peanut", "peanuts", "food"},
        "identity": {"name", "call", "called", "dave", "david"},
        "work": {"work", "startup", "engineer", "manager", "job", "company", "tech"},
        "hobby": {"hiking", "hike", "hobby", "enjoy"},
    }
    for concept, keywords in concepts.items():
        if any(keyword in tokens for keyword in keywords):
            expanded.append(f"concept:{concept}")

    return expanded
