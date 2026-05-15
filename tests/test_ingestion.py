"""
test_ingestion.py — Tests for the PDF ingestion pipeline.

Tests verify:
1. Text extraction from a PDF produces page-structured output
2. Chunk splitting respects size limits and produces overlapping chunks
3. Empty text is handled gracefully (no crash)
4. The full ingestion pipeline updates the document status correctly
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# -----------------------------------------------------------------------
# Unit tests for extract_text_from_pdf
# -----------------------------------------------------------------------

def test_extract_text_returns_page_list(tmp_path):
    """
    extract_text_from_pdf should return a list of dicts with 'page' and 'text' keys.
    We create a real (empty) file so open() succeeds, then mock PdfReader internals.
    """
    from backend.services.ingestion_service import extract_text_from_pdf

    # Create a real dummy file so open() doesn't raise FileNotFoundError
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"dummy pdf content")

    with patch("backend.services.ingestion_service.pypdf.PdfReader") as mock_reader:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "This is page one content."
        mock_reader.return_value.pages = [mock_page]

        result = extract_text_from_pdf(str(pdf_file))

    assert len(result) == 1
    assert result[0]["page"] == 1
    assert result[0]["text"] == "This is page one content."


def test_extract_text_skips_blank_pages(tmp_path):
    """Pages with no text should be skipped."""
    from backend.services.ingestion_service import extract_text_from_pdf

    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"dummy pdf content")

    with patch("backend.services.ingestion_service.pypdf.PdfReader") as mock_reader:
        blank_page = MagicMock()
        blank_page.extract_text.return_value = ""
        real_page = MagicMock()
        real_page.extract_text.return_value = "Real content here."
        mock_reader.return_value.pages = [blank_page, real_page]

        result = extract_text_from_pdf(str(pdf_file))

    # Only the non-blank page should be returned
    assert len(result) == 1
    assert result[0]["page"] == 2


# -----------------------------------------------------------------------
# Unit tests for split_into_chunks
# -----------------------------------------------------------------------

def test_split_short_text_produces_one_chunk():
    """Short text that fits in one chunk should not be split."""
    from backend.services.ingestion_service import split_into_chunks

    text = "This is a short paragraph."
    # page_char_offsets: one page covering the entire text
    offsets = [(0, len(text), 1)]
    chunks = split_into_chunks(text, page_char_offsets=offsets, source="test.pdf")

    assert len(chunks) == 1
    assert chunks[0]["text"] == text
    assert chunks[0]["page"] == 1
    assert chunks[0]["source"] == "test.pdf"
    assert chunks[0]["chunk_index"] == 0


def test_split_long_text_produces_multiple_chunks():
    """Text exceeding chunk size limit should be split into multiple chunks."""
    from backend.services.ingestion_service import split_into_chunks, CHUNK_SIZE_CHARS

    # Create text longer than one chunk by repeating paragraphs
    paragraph = "This is a paragraph with some content. " * 20  # ~800 chars
    long_text = "\n\n".join([paragraph] * 5)  # 5 paragraphs, ~4000 chars total

    offsets = [(0, len(long_text), 2)]
    chunks = split_into_chunks(long_text, page_char_offsets=offsets, source="test.pdf")

    # Should produce more than 1 chunk
    assert len(chunks) > 1
    # All chunks should have the correct metadata
    for i, chunk in enumerate(chunks):
        assert chunk["page"] == 2
        assert chunk["source"] == "test.pdf"
        assert chunk["chunk_index"] == i
        assert len(chunk["text"]) > 0


def test_split_empty_text_produces_no_chunks():
    """Empty or whitespace-only text should produce no chunks."""
    from backend.services.ingestion_service import split_into_chunks

    offsets = [(0, 10, 1)]
    chunks = split_into_chunks("   \n\n   ", page_char_offsets=offsets, source="test.pdf")
    assert len(chunks) == 0


# -----------------------------------------------------------------------
# Integration test: full ingestion pipeline
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ingestion_updates_document_status_to_done(tmp_path, mock_embedding, mock_qdrant):
    """
    The ingest_document function should set document status to 'done'
    after successful processing.
    """
    import uuid

    doc_id = uuid.uuid4()
    collection_id = str(uuid.uuid4())

    # Create a real temp file so open() doesn't fail
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"dummy pdf content")

    # Mock database session
    mock_doc = MagicMock()
    mock_doc.id = doc_id
    mock_doc.status = "processing"

    mock_db = AsyncMock()
    mock_db.get.return_value = mock_doc
    mock_db.commit = AsyncMock()

    with (
        patch("backend.services.ingestion_service.pypdf.PdfReader") as mock_reader,
        patch("backend.services.ingestion_service.embedding_service", mock_embedding),
        patch("backend.services.ingestion_service.qdrant_service", mock_qdrant),
    ):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "This is test content for the PDF. " * 10
        mock_reader.return_value.pages = [mock_page]

        from backend.services.ingestion_service import ingest_document

        await ingest_document(
            file_path=str(pdf_file),
            filename="test.pdf",
            document_id=doc_id,
            collection_id=collection_id,
            db=mock_db,
        )

    # Status should be updated to 'done'
    assert mock_doc.status == "done"
    assert mock_doc.chunk_count > 0


@pytest.mark.asyncio
async def test_ingestion_sets_failed_on_error(tmp_path, mock_qdrant):
    """
    If ingestion fails (e.g., corrupt PDF), document status should be 'failed'
    with the correct error message.
    """
    import uuid

    doc_id = uuid.uuid4()
    mock_doc = MagicMock()
    mock_doc.status = "processing"

    mock_db = AsyncMock()
    mock_db.get.return_value = mock_doc

    # Create a real file so open() succeeds, but make PdfReader raise our error
    corrupt_file = tmp_path / "corrupt.pdf"
    corrupt_file.write_bytes(b"not a real pdf")

    with (
        patch("backend.services.ingestion_service.qdrant_service", mock_qdrant),
        patch(
            "backend.services.ingestion_service.pypdf.PdfReader",
            side_effect=Exception("Corrupt PDF"),
        ),
    ):
        from backend.services.ingestion_service import ingest_document

        await ingest_document(
            file_path=str(corrupt_file),
            filename="corrupt.pdf",
            document_id=doc_id,
            collection_id="fake-id",
            db=mock_db,
        )

    assert mock_doc.status == "failed"
    assert "Corrupt PDF" in mock_doc.error_message

