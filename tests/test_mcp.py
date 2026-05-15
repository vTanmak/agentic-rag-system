"""
test_mcp.py — Tests for the MCP tool server.

Tests verify:
1. search_documents: valid input returns results
2. search_documents: empty query raises ValueError
3. search_documents: too-long query raises ValueError
4. search_documents: invalid UUID raises ValueError
5. get_document_metadata: invalid UUID raises ValueError
6. web_search: empty query raises ValueError
7. web_search: max_results out of range raises ValueError
8. Input validation helper functions work correctly
"""

import pytest
import uuid
from unittest.mock import AsyncMock, patch, MagicMock


# -----------------------------------------------------------------------
# Input validation helper tests (pure unit tests — no external calls)
# -----------------------------------------------------------------------

def test_validate_query_rejects_empty():
    from mcp_server.server import _validate_query
    with pytest.raises(ValueError, match="cannot be empty"):
        _validate_query("")


def test_validate_query_rejects_whitespace_only():
    from mcp_server.server import _validate_query
    with pytest.raises(ValueError, match="cannot be empty"):
        _validate_query("   ")


def test_validate_query_rejects_too_long():
    from mcp_server.server import _validate_query, MAX_INPUT_LENGTH
    with pytest.raises(ValueError, match="too long"):
        _validate_query("a" * (MAX_INPUT_LENGTH + 1))


def test_validate_query_accepts_valid_input():
    from mcp_server.server import _validate_query
    # Should not raise
    _validate_query("What is the main topic of this document?")


def test_validate_uuid_rejects_invalid():
    from mcp_server.server import _validate_uuid
    with pytest.raises(ValueError, match="valid UUID"):
        _validate_uuid("not-a-uuid")


def test_validate_uuid_rejects_empty():
    from mcp_server.server import _validate_uuid
    with pytest.raises(ValueError, match="valid UUID"):
        _validate_uuid("")


def test_validate_uuid_accepts_valid():
    from mcp_server.server import _validate_uuid
    # Should not raise
    _validate_uuid(str(uuid.uuid4()))


# -----------------------------------------------------------------------
# search_documents tool tests
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_documents_valid_input(mock_embedding, mock_qdrant):
    """search_documents should return a list of results for valid input."""
    with (
        patch("mcp_server.server.embedding_service", mock_embedding),
        patch("mcp_server.server.qdrant_service", mock_qdrant),
    ):
        from mcp_server.server import search_documents

        results = await search_documents(
            query="test query",
            collection_id=str(uuid.uuid4()),
            top_k=3,
        )

    assert isinstance(results, list)
    assert len(results) > 0
    assert "text" in results[0]
    assert "source" in results[0]


@pytest.mark.asyncio
async def test_search_documents_rejects_empty_query():
    from mcp_server.server import search_documents
    with pytest.raises(ValueError, match="cannot be empty"):
        await search_documents(query="", collection_id=str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_search_documents_rejects_invalid_uuid():
    from mcp_server.server import search_documents
    with pytest.raises(ValueError, match="valid UUID"):
        await search_documents(query="test", collection_id="not-a-uuid")


@pytest.mark.asyncio
async def test_search_documents_rejects_out_of_range_top_k(mock_embedding, mock_qdrant):
    from mcp_server.server import search_documents
    with pytest.raises(ValueError, match="top_k must be between"):
        await search_documents(
            query="test",
            collection_id=str(uuid.uuid4()),
            top_k=25,  # max is 20
        )


# -----------------------------------------------------------------------
# get_document_metadata tool tests
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_document_metadata_rejects_invalid_uuid():
    from mcp_server.server import get_document_metadata
    with pytest.raises(ValueError, match="valid UUID"):
        await get_document_metadata(doc_id="garbage")


@pytest.mark.asyncio
async def test_get_document_metadata_raises_on_not_found():
    """Should raise ValueError when document doesn't exist."""
    mock_session = AsyncMock()
    mock_session.get.return_value = None  # not found

    # async_session_factory is imported inside the function body in server.py,
    # so we patch it at the source module (database.py), not at mcp_server.server
    with patch("backend.models.database.async_session_factory") as mock_factory:
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        from mcp_server.server import get_document_metadata

        with pytest.raises(ValueError, match="not found"):
            await get_document_metadata(doc_id=str(uuid.uuid4()))


# -----------------------------------------------------------------------
# web_search tool tests
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_web_search_rejects_empty_query():
    from mcp_server.server import web_search
    with pytest.raises(ValueError, match="cannot be empty"):
        await web_search(query="")


@pytest.mark.asyncio
async def test_web_search_rejects_max_results_out_of_range():
    from mcp_server.server import web_search
    with pytest.raises(ValueError, match="max_results must be 1-10"):
        await web_search(query="test", max_results=15)


@pytest.mark.asyncio
async def test_web_search_returns_results():
    """web_search should return a list of dicts with title, url, snippet."""
    fake_results = [{"title": "Test", "href": "https://example.com", "body": "A test result"}]

    with patch("mcp_server.server.DDGS") as mock_ddgs:
        mock_ddgs.return_value.text.return_value = fake_results

        from mcp_server.server import web_search
        results = await web_search(query="test query", max_results=1)

    assert len(results) == 1
    assert results[0]["title"] == "Test"
    assert results[0]["url"] == "https://example.com"
    assert results[0]["snippet"] == "A test result"
