"""Base class for vector store implementations."""

import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from mind.ops_logger import ops

logger = logging.getLogger(__name__)


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

    Subclasses implement the ``_xxx`` variants (leading underscore).
    The public methods wrap them with unified ``📦 [VEC]`` logging.
    """

    @property
    def _vec_url(self) -> str:
        """Connection URL for logging. Falls back to ':memory:' if unset."""
        cfg = getattr(self, "config", None)
        return getattr(cfg, "url", None) or ":memory:"

    @abstractmethod
    def create_collection(self, dimensions: int) -> None:
        """Create or ensure the collection exists with the given vector size."""

    # ------------------------------------------------------------------
    # insert
    # ------------------------------------------------------------------

    def insert(
        self,
        id: str,
        vector: List[float],
        payload: Dict[str, Any],
    ) -> None:
        """Public entry-point for insert — logs and delegates."""
        collection = getattr(self, "collection_name", "?")
        t0 = time.perf_counter()
        try:
            self._insert(id=id, vector=vector, payload=payload)
        except Exception:
            elapsed = time.perf_counter() - t0
            ops.vec_error("INSERT", collection, self._vec_url, elapsed, id=id)
            raise
        elapsed = time.perf_counter() - t0
        ops.vec_op("INSERT", collection, self._vec_url, elapsed, id=id)

    @abstractmethod
    def _insert(
        self,
        id: str,
        vector: List[float],
        payload: Dict[str, Any],
    ) -> None:
        """Subclass implementation — insert a new vector with its payload."""

    # ------------------------------------------------------------------
    # search
    # ------------------------------------------------------------------

    def search(
        self,
        query_vector: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Public entry-point for search — logs and delegates."""
        collection = getattr(self, "collection_name", "?")
        t0 = time.perf_counter()
        try:
            results = self._search(query_vector=query_vector, limit=limit, filters=filters)
        except Exception:
            elapsed = time.perf_counter() - t0
            ops.vec_error("SEARCH", collection, self._vec_url, elapsed, limit=limit)
            raise
        elapsed = time.perf_counter() - t0
        ops.vec_op("SEARCH", collection, self._vec_url, elapsed, limit=limit, hits=len(results))
        return results

    @abstractmethod
    def _search(
        self,
        query_vector: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Subclass implementation — search for nearest vectors."""

    # ------------------------------------------------------------------
    # get
    # ------------------------------------------------------------------

    def get(self, id: str) -> Optional[Dict[str, Any]]:
        """Public entry-point for get — logs and delegates."""
        collection = getattr(self, "collection_name", "?")
        t0 = time.perf_counter()
        try:
            result = self._get(id)
        except Exception:
            elapsed = time.perf_counter() - t0
            ops.vec_error("GET", collection, self._vec_url, elapsed, id=id)
            raise
        elapsed = time.perf_counter() - t0
        found = "found" if result is not None else "miss"
        ops.vec_op("GET", collection, self._vec_url, elapsed, id=id, found=found)
        return result

    @abstractmethod
    def _get(self, id: str) -> Optional[Dict[str, Any]]:
        """Subclass implementation — retrieve a single record by ID."""

    # ------------------------------------------------------------------
    # list
    # ------------------------------------------------------------------

    def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Public entry-point for list — logs and delegates."""
        collection = getattr(self, "collection_name", "?")
        t0 = time.perf_counter()
        try:
            results = self._list(filters=filters, limit=limit)
        except Exception:
            elapsed = time.perf_counter() - t0
            ops.vec_error("LIST", collection, self._vec_url, elapsed, limit=limit)
            raise
        elapsed = time.perf_counter() - t0
        ops.vec_op("LIST", collection, self._vec_url, elapsed, limit=limit, count=len(results))
        return results

    @abstractmethod
    def _list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Subclass implementation — list records matching filters."""

    # ------------------------------------------------------------------
    # update
    # ------------------------------------------------------------------

    def update(
        self,
        id: str,
        vector: Optional[List[float]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Public entry-point for update — logs and delegates."""
        collection = getattr(self, "collection_name", "?")
        t0 = time.perf_counter()
        try:
            self._update(id=id, vector=vector, payload=payload)
        except Exception:
            elapsed = time.perf_counter() - t0
            ops.vec_error("UPDATE", collection, self._vec_url, elapsed, id=id)
            raise
        elapsed = time.perf_counter() - t0
        ops.vec_op("UPDATE", collection, self._vec_url, elapsed, id=id)

    @abstractmethod
    def _update(
        self,
        id: str,
        vector: Optional[List[float]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Subclass implementation — update a record's vector and/or payload."""

    # ------------------------------------------------------------------
    # delete
    # ------------------------------------------------------------------

    def delete(self, id: str) -> None:
        """Public entry-point for delete — logs and delegates."""
        collection = getattr(self, "collection_name", "?")
        t0 = time.perf_counter()
        try:
            self._delete(id)
        except Exception:
            elapsed = time.perf_counter() - t0
            ops.vec_error("DELETE", collection, self._vec_url, elapsed, id=id)
            raise
        elapsed = time.perf_counter() - t0
        ops.vec_op("DELETE", collection, self._vec_url, elapsed, id=id)

    @abstractmethod
    def _delete(self, id: str) -> None:
        """Subclass implementation — delete a record by ID."""
