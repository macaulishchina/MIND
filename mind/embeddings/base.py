"""Base class for embedding implementations."""

from abc import ABC, abstractmethod
from typing import List


class BaseEmbedding(ABC):
    """Abstract base for embedding backends."""

    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """Embed a single text string into a vector.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding vector.
        """
