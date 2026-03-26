"""Base class for LLM implementations."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseLLM(ABC):
    """Abstract base for LLM backends.

    The LLM layer is responsible for:
    - Extracting facts from conversations
    - Deciding memory operations (ADD/UPDATE/DELETE/NONE)
    - Assigning confidence scores to extracted facts
    """

    @abstractmethod
    def generate(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Generate a completion from the given messages.

        Args:
            messages: List of {"role": ..., "content": ...} dicts.
            response_format: Optional format specification (e.g., JSON mode).

        Returns:
            The assistant's response text.
        """
