import pytest
from unittest.mock import AsyncMock, MagicMock, patch

def test_extract_text_returns_page_list(tmp_path):
    # test pdf parsing
    from backend.services.ingestion_service import extract_text_from_pdf
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"dummy pdf content")

    with patch("backend.services.ingestion_service.pypdf.PdfReader") as mock_reader:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "This is page one content."
        mock_reader.return_value.pages = [mock_page]
        result = extract_text_from_pdf(str(pdf_file))

    assert len(result) == 1
    assert result[0]["page"] == 1

def test_extract_text_skips_blank_pages(tmp_path):
    # ignore image-only pages
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

    assert len(result) == 1
    assert result[0]["page"] == 2

def test_split_short_text_produces_one_chunk():
    # don't split tiny texts
    from backend.services.ingestion_service import split_into_chunks
    text = "This is a short paragraph."
    offsets = [(0, len(text), 1)]
    chunks = split_into_chunks(text, page_char_offsets=offsets, source="test.pdf")

    assert len(chunks) == 1
    assert chunks[0]["chunk_index"] == 0

def test_split_long_text_produces_multiple_chunks():
    # long text should be split into multiple chunks
    from backend.services.ingestion_service import split_into_chunks
    paragraph = "This is a paragraph with some content. " * 20
    long_text = "\n\n".join([paragraph] * 5)
    offsets = [(0, len(long_text), 2)]
    chunks = split_into_chunks(long_text, page_char_offsets=offsets, source="test.pdf")

    assert len(chunks) > 1

def test_split_empty_text_produces_no_chunks():
    # ignore blank text
    from backend.services.ingestion_service import split_into_chunks
    offsets = [(0, 10, 1)]
    chunks = split_into_chunks("   \n\n   ", page_char_offsets=offsets, source="test.pdf")
    assert len(chunks) == 0

@pytest.mark.asyncio
async def test_ingestion_updates_document_status_to_done(tmp_path, mock_embedding, mock_qdrant):
    # check successful pipeline run
    import uuid
    doc_id = uuid.uuid4()
    pdf_file = tmp_path / "test.pdf"
    pdf_file.write_bytes(b"dummy pdf content")

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
            collection_id=str(uuid.uuid4()),
            db=mock_db,
        )

    assert mock_doc.status == "done"

@pytest.mark.asyncio
async def test_ingestion_sets_failed_on_error(tmp_path, mock_qdrant):
    # check that corrupt pdfs fail cleanly
    import uuid
    doc_id = uuid.uuid4()
    mock_doc = MagicMock()
    mock_doc.status = "processing"

    mock_db = AsyncMock()
    mock_db.get.return_value = mock_doc
    corrupt_file = tmp_path / "corrupt.pdf"
    corrupt_file.write_bytes(b"not a real pdf")

    with (
        patch("backend.services.ingestion_service.qdrant_service", mock_qdrant),
        patch("backend.services.ingestion_service.pypdf.PdfReader", side_effect=Exception("Corrupt PDF")),
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
