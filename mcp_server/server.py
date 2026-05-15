
import asyncio
import os
import sys
import uuid
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastmcp import FastMCP
from duckduckgo_search import DDGS
from backend.config import get_settings
from backend.services.embedding_service import embedding_service
from backend.services.qdrant_service import qdrant_service

settings = get_settings()
mcp = FastMCP("Agentic RAG Tools")
MAX_INPUT_LENGTH = 5000

def _validate_query(query: str, field_name: str = "query") -> None:
    if not query or not query.strip():
        raise ValueError(f"{field_name} cannot be empty")
    if len(query) > MAX_INPUT_LENGTH:
        raise ValueError(
            f"{field_name} too long: {len(query)} chars (max {MAX_INPUT_LENGTH})"
        )

def _validate_uuid(value: str, field_name: str = "id") -> None:
    try:
        uuid.UUID(value)
    except ValueError:
        raise ValueError(f"{field_name} must be a valid UUID, got: {value!r}")

@mcp.tool()
async def search_documents(
    query: str,
    collection_id: str,
    top_k: int = 5,
) -> list[dict]:
    _validate_query(query, "query")
    _validate_uuid(collection_id, "collection_id")

    if not 1 <= top_k <= 20:
        raise ValueError(f"top_k must be between 1 and 20, got {top_k}")

    query_vector = await embedding_service.embed_text(query.strip())

    results = await qdrant_service.hybrid_search(
        collection_id=collection_id,
        query_vector=query_vector,
        query_text=query,
        top_k=top_k,
    )

    return results

@mcp.tool()
async def get_document_metadata(doc_id: str) -> dict:
    _validate_uuid(doc_id, "doc_id")

    from backend.models.database import Document, async_session_factory

    async with async_session_factory() as session:
        doc = await session.get(Document, uuid.UUID(doc_id))

    if doc is None:
        raise ValueError(f"Document not found: {doc_id}")

    return {
        "id": str(doc.id),
        "filename": doc.filename,
        "status": doc.status,
        "chunk_count": doc.chunk_count,
        "error_message": doc.error_message,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }

@mcp.tool()
async def web_search(query: str, max_results: int = 5) -> list[dict]:
    _validate_query(query, "query")

    if not 1 <= max_results <= 10:
        raise ValueError(f"max_results must be 1-10, got {max_results}")

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(
        None,
        lambda: list(DDGS().text(query.strip(), max_results=max_results)),
    )

    return [
        {
            "title": r.get("title", ""),
            "url": r.get("href", ""),
            "snippet": r.get("body", ""),
        }
        for r in results
    ]

@mcp.resource("collection://{collection_id}/stats")
async def collection_stats(collection_id: str) -> dict:
    _validate_uuid(collection_id, "collection_id")

    from backend.models.database import (
        Document, Collection, async_session_factory
    )
    from sqlalchemy import select, func

    async with async_session_factory() as session:
        doc_count_result = await session.execute(
            select(func.count(Document.id)).where(
                Document.collection_id == uuid.UUID(collection_id)
            )
        )
        doc_count = doc_count_result.scalar() or 0

        collection = await session.get(Collection, uuid.UUID(collection_id))
        collection_name = collection.name if collection else "unknown"

    chunk_count = await qdrant_service.get_chunk_count(collection_id)

    return {
        "collection_id": collection_id,
        "collection_name": collection_name,
        "document_count": doc_count,
        "chunk_count": chunk_count,
    }

if __name__ == "__main__":
    mcp.run()