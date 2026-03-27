"""Base class for LLM implementations."""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from mind.ops_logger import ops

logger = logging.getLogger(__name__)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English, ~2 for CJK-heavy."""
    return max(1, len(text) // 4)


class BaseLLM(ABC):
    """Abstract base for LLM backends.

    The LLM layer is responsible for:
    - Extracting facts from conversations
    - Deciding memory operations (ADD/UPDATE/DELETE/NONE)
    - Assigning confidence scores to extracted facts

    Subclasses must implement ``_generate`` (note the leading underscore).
    The public ``generate`` method wraps ``_generate`` with unified logging.
    """

    # Subclasses should set this in __init__ for accurate provider logging,
    # otherwise falls back to config.provider.
    provider: str = ""
    model: str = ""

    def generate(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict[str, Any]] = None,
        prompt_name: Optional[str] = None,
    ) -> str:
        """Public entry-point — delegates to ``_generate`` with logging.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            response_format: Optional format specification (e.g., JSON mode).
            prompt_name: Optional name of the prompt template used (e.g.
                ``"FACT_EXTRACTION"``). When provided and verbose logging is
                enabled, only the template name and user message preview are
                shown instead of the full system prompt.
        """
        provider = self.provider or getattr(getattr(self, "config", None), "provider", "?")
        model = self.model or getattr(getattr(self, "config", None), "model", "?")
        n_msgs = len(messages)

        # Estimate input tokens from message contents
        in_text = "".join(m.get("content", "") for m in messages)
        in_tokens = _estimate_tokens(in_text)

        t0 = time.perf_counter()
        try:
            result = self._generate(messages, response_format)
        except Exception:
            elapsed = time.perf_counter() - t0
            ops.llm_error(provider, model, n_msgs, in_tokens, elapsed)
            raise

        elapsed = time.perf_counter() - t0
        out_tokens = _estimate_tokens(result)

        ops.llm_call(
            provider, model, n_msgs, in_tokens, out_tokens, elapsed,
            prompt_name=prompt_name, messages=messages, response=result,
        )
        return result

    @abstractmethod
    def _generate(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Subclass implementation — perform the actual LLM call.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            response_format: Optional format specification (e.g., JSON mode).

        Returns:
            The assistant's response text.
        """
