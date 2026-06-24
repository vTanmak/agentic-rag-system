# test setup and fake services
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest_asyncio.fixture
async def test_client():
    # fake the database and qdrant so tests don't hit real servers
    with (
        patch("backend.models.database.create_async_engine"),
        patch("backend.services.qdrant_service.qdrant_service"),
    ):
        from backend.main import app
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client

@pytest.fixture
def mock_llm():
    # make sure ai always says yes for testing
    mock = AsyncMock()
    mock.generate.return_value = '{"sufficient": true, "reason": "context is sufficient", "refined_query": null}'

    async def mock_stream(*args, **kwargs):
        for token in ["The ", "answer ", "is ", "42."]:
            yield token

    mock.stream = mock_stream
    return mock

@pytest.fixture
def mock_qdrant():
    # fake search results from qdrant
    mock = AsyncMock()
    mock.hybrid_search.return_value = [
        {
            "source": "test.pdf",
            "page": 1,
            "chunk_index": 0,
            "text": "This is a test chunk with relevant information about the topic.",
            "text_preview": "This is a test chunk...",
            "score": 0.85,
        }
    ]
    mock.ensure_collection.return_value = None
    mock.upsert_chunks.return_value = None
    mock.get_chunk_count.return_value = 5
    mock.ping.return_value = True
    return mock

@pytest.fixture
def mock_embedding():
    # fake the embedding model output
    mock = AsyncMock()
    mock.embed_text.return_value = [0.1] * 384
    mock.embed_batch.return_value = [[0.1] * 384, [0.2] * 384]
    return mock

@pytest.fixture
def sample_pdf_bytes():
    # a tiny fake pdf file
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 << /Type /Font "
        b"/Subtype /Type1 /BaseFont /Helvetica >> >> >> >>\nendobj\n"
        b"4 0 obj\n<< /Length 44 >>\nstream\nBT /F1 12 Tf 100 700 Td "
        b"(Hello World) Tj ET\nendstream\nendobj\n"
        b"xref\n0 5\n0000000000 65535 f\n"
        b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n0\n%%EOF"
    )
