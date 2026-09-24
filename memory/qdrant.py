"""
Qdrant vector search client for OSS Work semantic memory.
Handles: embedding storage, similarity search, semantic recall.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import qdrant_client
from qdrant_client.models import (
    Distance,
    HnswIndexParams,
    PointStruct,
    SearchParams,
    VectorParams,
)


@dataclass
class QdrantConfig:
    url: str = "http://localhost:6333"
    api_key: str = ""
    collection: str = "oss_work_interactions"
    vector_size: int = 384  # Default embedding size


class QdrantClient:


    def __init__(self, config: QdrantConfig | None = None) -> None:
        self.config = config or QdrantConfig()
        self._client: qdrant_client.QdrantClient | None = None
        self._collection = self.config.collection

    async def connect(self) -> None:
        """Connect to Qdrant."""
        # Qdrant client is synchronous but we create it here
        self._client = qdrant_client.QdrantClient(
            url=self.config.url,
            api_key=self.config.api_key if self.config.api_key else None,
        )
        await self._ensure_collection()

    async def _ensure_collection(self) -> None:
        """Ensure the collection exists with proper configuration."""
        if not self._client:
            return
        try:
            self._client.get_collection(self._collection)
        except Exception:
            self._client.create_collection(
                collection_name=self._collection,
                vectors_config=VectorParams(
                    size=self.config.vector_size,
                    distance=Distance.COSINE,
                    on_disk=True,
                ),
                hnsw_index_params=HnswIndexParams(
                    m=16,
                    ef_construct=100,
                ),
            )

    async def close(self) -> None:
        """Close connection."""
        self._client = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    # ── Embedding Storage ─────────────────────────────────────

    async def store_embedding(self, point_id: int | str, vector: list[float],
                              payload: dict[str, Any]) -> None:
        """Store an embedding with its payload."""
        if not self._client:
            raise RuntimeError("Not connected")
        point = PointStruct(
            id=int(point_id) if isinstance(point_id, str) else point_id,
            vector=vector,
            payload=payload,
        )
        self._client.upsert(
            collection_name=self._collection,
            points=[point],
        )

    async def store_interaction(self, interaction_id: str, embedding: list[float],
                                task: str, user_id: str, result: dict,
                                agent_used: str, timestamp: datetime | None = None) -> None:
        """Store an interaction with semantic embedding."""
        payload = {
            "interaction_id": interaction_id,
            "task": task,
            "user_id": user_id,
            "result": result,
            "agent_used": agent_used,
            "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
        }
        await self.store_embedding(
            point_id=interaction_id,
            vector=embedding,
            payload=payload,
        )

    # ── Similarity Search ─────────────────────────────────────

    async def search_similar(
        self,
        query_vector: list[float],
        filter_user_id: str | None = None,
        limit: int = 5,
        min_score: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Find semantically similar interactions."""
        if not self._client:
            raise RuntimeError("Not connected")

        search_filter = None
        if filter_user_id:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="user_id",
                        match=MatchValue(value=filter_user_id),
                    )
                ]
            )

        results = self._client.search(
            collection_name=self._collection,
            query_vector=query_vector,
            limit=limit,
            score_threshold=min_score,
            query_filter=search_filter,
            search_params=SearchParams(hnsw_ef=64),
        )

        return [
            {
                "id": str(r.id),
                "score": r.score,
                "payload": r.payload,
            }
            for r in results
        ]

    async def recall_similar(
        self,
        user_id: str,
        query: str,
        embedding_fn: callable,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Find similar past interactions for a user."""
        vector = embedding_fn(query)
        return await self.search_similar(
            query_vector=vector,
            filter_user_id=user_id,
            limit=limit,
        )

    # ── Memory Operations ─────────────────────────────────────

    async def get_memory_stats(self) -> dict[str, Any]:
        """Get collection statistics."""
        if not self._client:
            raise RuntimeError("Not connected")
        info = self._client.get_collection(self._collection)
        return {
            "collection": self._collection,
            "vector_size": info.config.params.vectors.size,
            "points_count": info.points_count,
            "status": info.status,
        }

    async def delete_point(self, point_id: int | str) -> None:
        """Delete a specific point."""
        if not self._client:
            raise RuntimeError("Not connected")
        self._client.delete_points(
            collection_name=self._collection,
            points_selector=[int(point_id) if isinstance(point_id, str) else point_id],
        )

    async def delete_user_points(self, user_id: str) -> None:
        """Delete all points for a user."""
        if not self._client:
            raise RuntimeError("Not connected")
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        self._client.delete_points(
            collection_name=self._collection,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="user_id",
                        match=MatchValue(value=user_id),
                    )
                ]
            ),
        )

    # ── Health Check ───────────────────────────────────────────

    async def health_check(self) -> dict[str, Any]:
        try:
            if not self._client:
                return {"status": "disconnected"}
            self._client.get_collection(self._collection)
            return {"status": "healthy"}
        except Exception as e:
            return {"status": "error", "error": str(e)}


# ── Default Embedding (identity-based for testing) ────────────

def simple_embedding(text: str, size: int = 384) -> list[float]:
    """
    Simple deterministic embedding for testing.
    In production, replace with a real embedding model.
    """
    import hashlib
    import math

    hash_bytes = hashlib.sha256(text.encode()).digest()
    vector = []
    for i in range(size):
        byte_idx = i % len(hash_bytes)
        val = hash_bytes[byte_idx] / 255.0
        # Add some variation based on position
        val = val + (i * 0.001) % 1.0
        vector.append(min(val, 1.0))
    # Normalize
    norm = math.sqrt(sum(v * v for v in vector))
    if norm > 0:
        vector = [v / norm for v in vector]
    return vector
