import pytest
import uuid
from unittest.mock import patch, AsyncMock

def test_validate_query_rejects_empty():
    # make sure empty searches fail
    from mcp_server.server import _validate_query
    with pytest.raises(ValueError, match="cannot be empty"):
        _validate_query("")

def test_validate_query_rejects_whitespace_only():
    # make sure space-only searches fail
    from mcp_server.server import _validate_query
    with pytest.raises(ValueError, match="cannot be empty"):
        _validate_query("   ")

def test_validate_query_rejects_too_long():
    # prevent massive prompt injection crashes
    from mcp_server.server import _validate_query, MAX_INPUT_LENGTH
    with pytest.raises(ValueError, match="too long"):
        _validate_query("a" * (MAX_INPUT_LENGTH + 1))

def test_validate_query_accepts_valid_input():
    # normal searches should pass
    from mcp_server.server import _validate_query
    _validate_query("What is the main topic of this document?")

def test_validate_uuid_rejects_invalid():
    # block fake uuids
    from mcp_server.server import _validate_uuid
    with pytest.raises(ValueError, match="valid UUID"):
        _validate_uuid("not-a-uuid")

def test_validate_uuid_rejects_empty():
    # block empty uuids
    from mcp_server.server import _validate_uuid
    with pytest.raises(ValueError, match="valid UUID"):
        _validate_uuid("")

def test_validate_uuid_accepts_valid():
    # real uuids should pass
    from mcp_server.server import _validate_uuid
    _validate_uuid(str(uuid.uuid4()))

@pytest.mark.asyncio
async def test_search_documents_valid_input(mock_embedding, mock_qdrant):
    # test document search tool works
    with (
        patch("mcp_server.server.embedding_service", mock_embedding),
        patch("mcp_server.server.qdrant_service", mock_qdrant),
    ):
        from mcp_server.server import search_documents
        results = await search_documents(query="test query", collection_id=str(uuid.uuid4()), top_k=3)

    assert isinstance(results, list)
    assert len(results) > 0
    assert "text" in results[0]

@pytest.mark.asyncio
async def test_search_documents_rejects_empty_query():
    # search shouldn't run if query is empty
    from mcp_server.server import search_documents
    with pytest.raises(ValueError, match="cannot be empty"):
        await search_documents(query="", collection_id=str(uuid.uuid4()))

@pytest.mark.asyncio
async def test_search_documents_rejects_invalid_uuid():
    # search shouldn't run if id is bad
    from mcp_server.server import search_documents
    with pytest.raises(ValueError, match="valid UUID"):
        await search_documents(query="test", collection_id="not-a-uuid")

@pytest.mark.asyncio
async def test_search_documents_rejects_out_of_range_top_k(mock_embedding, mock_qdrant):
    # prevent asking for too many results
    from mcp_server.server import search_documents
    with pytest.raises(ValueError, match="top_k must be between"):
        await search_documents(query="test", collection_id=str(uuid.uuid4()), top_k=25)

@pytest.mark.asyncio
async def test_get_document_metadata_rejects_invalid_uuid():
    # check metadata tool blocks bad ids
    from mcp_server.server import get_document_metadata
    with pytest.raises(ValueError, match="valid UUID"):
        await get_document_metadata(doc_id="garbage")

@pytest.mark.asyncio
async def test_get_document_metadata_raises_on_not_found():
    # metadata tool should error if doc doesn't exist
    mock_session = AsyncMock()
    mock_session.get.return_value = None

    with patch("backend.models.database.async_session_factory") as mock_factory:
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        from mcp_server.server import get_document_metadata
        with pytest.raises(ValueError, match="not found"):
            await get_document_metadata(doc_id=str(uuid.uuid4()))

@pytest.mark.asyncio
async def test_web_search_rejects_empty_query():
    # web search tool needs a real query
    from mcp_server.server import web_search
    with pytest.raises(ValueError, match="cannot be empty"):
        await web_search(query="")

@pytest.mark.asyncio
async def test_web_search_rejects_max_results_out_of_range():
    # limit web search results
    from mcp_server.server import web_search
    with pytest.raises(ValueError, match="max_results must be 1-10"):
        await web_search(query="test", max_results=15)

@pytest.mark.asyncio
async def test_web_search_returns_results():
    # check web search actually returns stuff
    fake_results = [{"title": "Test", "href": "https://example.com", "body": "A test result"}]

    with patch("mcp_server.server.DDGS") as mock_ddgs:
        mock_ddgs.return_value.text.return_value = fake_results
        from mcp_server.server import web_search
        results = await web_search(query="test query", max_results=1)

    assert len(results) == 1
    assert results[0]["title"] == "Test"
