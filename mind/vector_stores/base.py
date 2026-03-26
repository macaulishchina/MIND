"""Base class for vector store implementations."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class BaseVectorStore(ABC):
    """Abstract base for vector store backends.

    Each implementation must support:
    - Creating / ensuring a collection exists
    - Inserting a vector with payload
    - Searching by vector with optional metadata filters
    - Retrieving a single record by ID
    - Listing records with optional metadata filters
    - Updating a record's vector and payload
    - Deleting a record by ID
    """

    @abstractmethod
    def create_collection(self, dimensions: int) -> None:
        """Create or ensure the collection exists with the given vector size."""

    @abstractmethod
    def insert(
        self,
        id: str,
        vector: List[float],
        payload: Dict[str, Any],
    ) -> None:
        """Insert a new vector with its payload."""

    @abstractmethod
    def search(
        self,
        query_vector: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search for the nearest vectors.

        Returns a list of dicts, each containing at least:
        - id: str
        - score: float
        - payload: Dict[str, Any]
        """

    @abstractmethod
    def get(self, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single record by ID.

        Returns a dict with id, vector (optional), and payload, or None.
        """

    @abstractmethod
    def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List records matching the given filters."""

    @abstractmethod
    def update(
        self,
        id: str,
        vector: Optional[List[float]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update a record's vector and/or payload."""

    @abstractmethod
    def delete(self, id: str) -> None:
        """Delete a record by ID."""
