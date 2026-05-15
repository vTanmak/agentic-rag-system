import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.database import Collection, Document, get_db_session
from backend.models.schemas import CollectionCreate,CollectionListResponse,CollectionResponse
from backend.services.qdrant_service import qdrant_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/collections", tags=["Collections"])

@router.post(
    "",
    response_model=CollectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_collection(
    body: CollectionCreate,
    db: AsyncSession = Depends(get_db_session),
):
    existing = await db.execute(
        select(Collection).where(Collection.name == body.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A collection named '{body.name}' already exists",
        )

    new_collection = Collection(name=body.name)
    db.add(new_collection)
    await db.flush()
    await db.refresh(new_collection)

    logger.info(f"Created collection: {new_collection.name} ({new_collection.id})")
    return new_collection

@router.get("", response_model=CollectionListResponse)
async def list_collections(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(
        select(Collection).order_by(Collection.created_at.desc())
    )
    collections = result.scalars().all()

    return CollectionListResponse(
        collections=list(collections),
        total=len(collections),
    )

@router.get("/{collection_id}", response_model=CollectionResponse)
async def get_collection(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    collection = await db.get(Collection, collection_id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Collection {collection_id} not found",
        )
    return collection

@router.get("/{collection_id}/documents")
async def list_collection_documents(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(Document)
        .where(Document.collection_id == collection_id)
        .order_by(Document.created_at.desc())
    )
    docs = result.scalars().all()
    return {
        "documents": [
            {
                "id": str(d.id),
                "filename": d.filename,
                "status": d.status,
                "chunk_count": d.chunk_count,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ]
    }

@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    collection = await db.get(Collection, collection_id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Collection {collection_id} not found",
        )

    await qdrant_service.delete_collection(str(collection_id))

    await db.delete(collection)
    await db.commit()

    logger.info(f"Deleted collection {collection_id}")