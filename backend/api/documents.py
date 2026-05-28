import logging
import os
import uuid
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.database import Collection, Document, async_session_factory, get_db_session
from backend.models.schemas import DocumentStatusResponse, DocumentUploadResponse
from backend.services.ingestion_service import ingest_document
from backend.api.deps import get_user_id

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

router = APIRouter(prefix="/api/v1", tags=["Documents"])

@router.post(
    "/collections/{collection_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def upload_document(
    collection_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_user_id),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db_session),
):
    collection = await db.get(Collection, collection_id)
    if not collection or collection.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Collection {collection_id} not found",
        )

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported",
        )

    doc_id = uuid.uuid4()
    safe_filename = f"{doc_id}_{file.filename}"
    file_path = UPLOAD_DIR / safe_filename

    try:
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {e}",
        )

    doc = Document(
        id=doc_id,
        collection_id=collection_id,
        filename=file.filename,
        status="processing",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    background_tasks.add_task(
        _run_ingestion_background,
        file_path=str(file_path),
        filename=file.filename,
        document_id=doc_id,
        collection_id=str(collection_id),
    )

    logger.info(f"Document queued for ingestion: {file.filename} ({doc_id})")

    return DocumentUploadResponse(
        document_id=doc_id,
        filename=file.filename,
        status="processing",
    )

async def _run_ingestion_background(
    file_path: str,
    filename: str,
    document_id: uuid.UUID,
    collection_id: str,
) -> None:
    async with async_session_factory() as session:
        await ingest_document(
            file_path=file_path,
            filename=filename,
            document_id=document_id,
            collection_id=collection_id,
            db=session,
        )

@router.get("/documents/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: uuid.UUID,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )
        
    collection = await db.get(Collection, doc.collection_id)
    if not collection or collection.user_id != user_id:
        raise HTTPException(status_code=404, detail="Document not found")

    return DocumentStatusResponse(
        document_id=doc.id,
        filename=doc.filename,
        status=doc.status,
        chunk_count=doc.chunk_count,
        error_message=doc.error_message,
        created_at=doc.created_at,
    )

@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    from backend.services.qdrant_service import qdrant_service

    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document {document_id} not found",
        )

    collection = await db.get(Collection, doc.collection_id)
    if not collection or collection.user_id != user_id:
        raise HTTPException(status_code=404, detail="Document not found")

    await qdrant_service.delete_document_chunks(
        collection_id=str(doc.collection_id),
        filename=doc.filename,
    )

    try:
        for f in UPLOAD_DIR.glob(f"*_{doc.filename}"):
            f.unlink(missing_ok=True)
    except Exception:
        pass

    await db.delete(doc)
    await db.commit()

    logger.info(f"Deleted document {document_id} ({doc.filename})")