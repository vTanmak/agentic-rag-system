
import logging
import re
import uuid
from pathlib import Path
from typing import Any

import pypdf
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.database import Document
from backend.services.embedding_service import embedding_service
from backend.services.qdrant_service import qdrant_service

logger = logging.getLogger(__name__)


CHUNK_SIZE_TOKENS = 400
OVERLAP_TOKENS = 50
CHARS_PER_TOKEN = 4

CHUNK_SIZE_CHARS = CHUNK_SIZE_TOKENS * CHARS_PER_TOKEN
OVERLAP_CHARS = OVERLAP_TOKENS * CHARS_PER_TOKEN


def extract_text_from_pdf(file_path: str) -> list[dict[str, Any]]:
    pages = []
    with open(file_path, "rb") as f:
        reader = pypdf.PdfReader(f)
        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append({"page": page_num, "text": text.strip()})
    return pages


def split_into_chunks(
    full_text: str,
    page_char_offsets: list[tuple[int, int, int]],
    source: str,
) -> list[dict[str, Any]]:
    full_text = re.sub(r"\n{3,}", "\n\n", full_text)

    paragraphs = [p.strip() for p in full_text.split("\n\n") if p.strip()]

    chunks = []
    current_chunk = ""
    current_char_pos = 0
    chunk_index = 0

    for paragraph in paragraphs:
        if len(current_chunk) + len(paragraph) > CHUNK_SIZE_CHARS and current_chunk:
            chunk_page = _find_page_for_position(current_char_pos, page_char_offsets)
            chunks.append({
                "text": current_chunk.strip(),
                "page": chunk_page,
                "source": source,
                "chunk_index": chunk_index,
            })
            chunk_index += 1
            current_chunk = current_chunk[-OVERLAP_CHARS:] + "\n\n" + paragraph
        else:
            current_chunk = current_chunk + "\n\n" + paragraph if current_chunk else paragraph

        para_pos = full_text.find(paragraph, current_char_pos)
        if para_pos >= 0:
            current_char_pos = para_pos

    if current_chunk.strip():
        chunk_page = _find_page_for_position(current_char_pos, page_char_offsets)
        chunks.append({
            "text": current_chunk.strip(),
            "page": chunk_page,
            "source": source,
            "chunk_index": chunk_index,
        })

    return chunks


def _find_page_for_position(
    char_pos: int,
    page_char_offsets: list[tuple[int, int, int]],
) -> int:
    for start, end, page_num in page_char_offsets:
        if start <= char_pos < end:
            return page_num
    return page_char_offsets[-1][2] if page_char_offsets else 1


async def ingest_document(
    file_path: str,
    filename: str,
    document_id: uuid.UUID,
    collection_id: str,
    db: AsyncSession,
) -> None:
    try:
        await qdrant_service.ensure_collection(collection_id)

        logger.info(f"Extracting text from {filename}")
        pages = extract_text_from_pdf(file_path)

        if not pages:
            raise ValueError("PDF has no extractable text (may be a scanned image PDF)")

        full_text = ""
        page_char_offsets = []
        for page_data in pages:
            start = len(full_text)
            full_text += page_data["text"] + "\n\n"
            end = len(full_text)
            page_char_offsets.append((start, end, page_data["page"]))

        all_chunks = split_into_chunks(
            full_text=full_text,
            page_char_offsets=page_char_offsets,
            source=filename,
        )

        logger.info(f"Split {filename} into {len(all_chunks)} chunks")

        if not all_chunks:
            raise ValueError("No chunks generated from the document")

        chunk_texts = [c["text"] for c in all_chunks]
        embeddings = await embedding_service.embed_batch(chunk_texts)

        for chunk, embedding in zip(all_chunks, embeddings):
            chunk["embedding"] = embedding

        await qdrant_service.upsert_chunks(collection_id, all_chunks)

        doc = await db.get(Document, document_id)
        if doc:
            doc.status = "done"
            doc.chunk_count = len(all_chunks)
            await db.commit()

        logger.info(f"Ingestion complete: {filename} → {len(all_chunks)} chunks")

    except Exception as e:
        logger.error(f"Ingestion failed for {filename}: {e}")
        doc = await db.get(Document, document_id)
        if doc:
            doc.status = "failed"
            doc.error_message = str(e)
            await db.commit()
    finally:
        try:
            Path(file_path).unlink(missing_ok=True)
        except Exception:
            pass
