import logging
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels
from backend.config import get_settings
from backend.services.embedding_service import EMBEDDING_DIM

logger = logging.getLogger(__name__)
settings = get_settings()

class QdrantService:
    def __init__(self):
        self._client = AsyncQdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key or None,
        )

    async def ensure_collection(self, collection_id: str) -> None:
        collection_name = self._collection_name(collection_id)
        existing = await self._client.collection_exists(collection_name)
        if existing:
            return

        await self._client.create_collection(
            collection_name=collection_name,
            vectors_config=qmodels.VectorParams(
                size=EMBEDDING_DIM,
                distance=qmodels.Distance.COSINE,
            ),
        )
        logger.info(f"Created Qdrant collection: {collection_name}")

    async def upsert_chunks(
        self,
        collection_id: str,
        chunks: list[dict[str, Any]],
    ) -> None:
        collection_name = self._collection_name(collection_id)

        points = [
            qmodels.PointStruct(
                id=str(uuid.uuid4()),
                vector=chunk["embedding"],
                payload={
                    "source": chunk["source"],
                    "collection_id": collection_id,
                    "page": chunk["page"],
                    "chunk_index": chunk["chunk_index"],
                    "text_preview": chunk["text"][:100],
                    "text": chunk["text"],
                },
            )
            for chunk in chunks
        ]

        await self._client.upsert(
            collection_name=collection_name,
            points=points,
        )
        logger.info(f"Upserted {len(points)} chunks into {collection_name}")

    async def hybrid_search(
        self,
        collection_id: str,
        query_vector: list[float],
        query_text: str,
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        collection_name = self._collection_name(collection_id)

        if not await self._client.collection_exists(collection_name):
            logger.warning(f"Collection {collection_name} not found in Qdrant")
            return []

        response = await self._client.query_points(
            collection_name=collection_name,
            query=query_vector,
            limit=top_k,
            with_payload=True,
        )

        return [
            {
                "source": r.payload.get("source", ""),
                "collection_id": r.payload.get("collection_id", ""),
                "page": r.payload.get("page", 0),
                "chunk_index": r.payload.get("chunk_index", 0),
                "text_preview": r.payload.get("text_preview", ""),
                "text": r.payload.get("text", ""),
                "score": r.score,
            }
            for r in response.points
        ]

    async def delete_collection(self, collection_id: str) -> None:
        collection_name = self._collection_name(collection_id)
        if await self._client.collection_exists(collection_name):
            await self._client.delete_collection(collection_name)
            logger.info(f"Deleted Qdrant collection: {collection_name}")

    async def delete_document_chunks(self, collection_id: str, filename: str) -> None:
        collection_name = self._collection_name(collection_id)
        if not await self._client.collection_exists(collection_name):
            return
        await self._client.delete(
            collection_name=collection_name,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="source",
                            match=qmodels.MatchValue(value=filename),
                        )
                    ]
                )
            ),
        )
        logger.info(f"Deleted chunks for '{filename}' from {collection_name}")

    async def get_chunk_count(self, collection_id: str) -> int:
        collection_name = self._collection_name(collection_id)
        if not await self._client.collection_exists(collection_name):
            return 0
        info = await self._client.get_collection(collection_name)
        return info.points_count or 0

    async def ping(self) -> bool:
        try:
            await self._client.get_collections()
            return True
        except Exception as e:
            logger.error(f"Qdrant ping failed: {e}")
            return False

    @staticmethod
    def _collection_name(collection_id: str) -> str:
        return f"rag_{collection_id}"

qdrant_service = QdrantService()