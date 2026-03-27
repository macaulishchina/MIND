"""Base class for embedding implementations."""

import logging
import time
from abc import ABC, abstractmethod
from typing import List

from mind.ops_logger import ops

logger = logging.getLogger(__name__)


class BaseEmbedding(ABC):
    """Abstract base for embedding backends.

    Subclasses must implement ``_embed`` (note the leading underscore).
    The public ``embed`` method wraps ``_embed`` with unified logging.
    """

    def embed(self, text: str) -> List[float]:
        """Public entry-point — delegates to ``_embed`` with logging."""
        cfg = getattr(self, "config", None)
        provider = getattr(cfg, "protocols", "?")
        model = getattr(cfg, "model", "?")
        text_len = len(text)

        t0 = time.perf_counter()
        try:
            vector = self._embed(text)
        except Exception:
            elapsed = time.perf_counter() - t0
            ops.emb_error(provider, model, text_len, elapsed)
            raise

        elapsed = time.perf_counter() - t0
        ops.emb_call(
            provider, model, text_len, len(vector), elapsed,
            text=text, vector_preview=vector,
        )
        return vector

    @abstractmethod
    def _embed(self, text: str) -> List[float]:
        """Subclass implementation — perform the actual embedding call.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding vector.
        """
