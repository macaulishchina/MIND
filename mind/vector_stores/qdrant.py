"""Qdrant vector store implementation."""

import logging
from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointIdsList,
    PointStruct,
    VectorParams,
)

from mind.config.schema import VectorStoreConfig
from mind.vector_stores.base import BaseVectorStore

logger = logging.getLogger(__name__)


class QdrantVectorStore(BaseVectorStore):
    """Qdrant-backed vector store.

    Supports both in-memory mode (url=None) for development and
    server mode (url set) for production.
    """

    def __init__(self, config: VectorStoreConfig) -> None:
        self.config = config
        self.collection_name = config.collection_name

        if config.url:
            self.client = QdrantClient(
                url=config.url,
                api_key=config.api_key,
            )
        else:
            # In-memory mode for development / testing
            self.client = QdrantClient(location=":memory:")

    def create_collection(self, dimensions: int) -> None:
        """Create the collection if it does not already exist."""
        collections = self.client.get_collections().collections
        existing_names = {c.name for c in collections}

        if self.collection_name not in existing_names:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=dimensions,
                    distance=Distance.COSINE,
                    on_disk=self.config.on_disk,
                ),
            )
            logger.info(
                "Created Qdrant collection %s (dim=%d)",
                self.collection_name,
                dimensions,
            )

    def insert(
        self,
        id: str,
        vector: List[float],
        payload: Dict[str, Any],
    ) -> None:
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                PointStruct(id=id, vector=vector, payload=payload),
            ],
        )

    def search(
        self,
        query_vector: List[float],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        qdrant_filter = self._build_filter(filters) if filters else None

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=limit,
            query_filter=qdrant_filter,
        )

        return [
            {
                "id": point.id,
                "score": point.score,
                "payload": point.payload or {},
            }
            for point in response.points
        ]

    def get(self, id: str) -> Optional[Dict[str, Any]]:
        results = self.client.retrieve(
            collection_name=self.collection_name,
            ids=[id],
            with_payload=True,
        )
        if not results:
            return None

        point = results[0]
        return {
            "id": point.id,
            "payload": point.payload or {},
        }

    def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        qdrant_filter = self._build_filter(filters) if filters else None

        records, _offset = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=qdrant_filter,
            limit=limit,
            with_payload=True,
        )

        return [
            {
                "id": record.id,
                "payload": record.payload or {},
            }
            for record in records
        ]

    def update(
        self,
        id: str,
        vector: Optional[List[float]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        if payload is not None:
            self.client.set_payload(
                collection_name=self.collection_name,
                payload=payload,
                points=[id],
            )

        if vector is not None:
            # Re-upsert with the new vector; preserve existing payload
            existing = self.get(id)
            merged_payload = existing["payload"] if existing else {}
            if payload:
                merged_payload.update(payload)
            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(id=id, vector=vector, payload=merged_payload),
                ],
            )

    def delete(self, id: str) -> None:
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=PointIdsList(points=[id]),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_filter(filters: Dict[str, Any]) -> Filter:
        """Build a Qdrant Filter from a simple key-value dict."""
        conditions = []
        for key, value in filters.items():
            conditions.append(
                FieldCondition(key=key, match=MatchValue(value=value))
            )
        return Filter(must=conditions)
