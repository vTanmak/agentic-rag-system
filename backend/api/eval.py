import logging
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.models.database import (
    Collection,
    ConversationSession,
    Message,
    get_db_session,
)
from backend.models.schemas import EvalReport

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/collections", tags=["Evaluation"])


@router.get("/{collection_id}/eval-report", response_model=EvalReport)
async def get_eval_report(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
):
    collection = await db.get(Collection, collection_id)
    if not collection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Collection {collection_id} not found",
        )

    sessions_result = await db.execute(
        select(ConversationSession.id).where(
            ConversationSession.collection_id == collection_id
        )
    )
    session_ids = [row[0] for row in sessions_result.all()]

    if not session_ids:
        return EvalReport(collection_id=collection_id, message_count=0)

    messages_result = await db.execute(
        select(Message)
        .where(
            Message.session_id.in_(session_ids),
            Message.role == "assistant",
            Message.eval_scores_json.isnot(None),
        )
        .order_by(Message.created_at.desc())
        .limit(50)
    )
    messages = messages_result.scalars().all()

    if not messages:
        return EvalReport(collection_id=collection_id, message_count=0)

    faithfulness_scores = []
    relevancy_scores = []
    recall_scores = []
    precision_scores = []

    for msg in messages:
        scores = msg.eval_scores_json or {}
        if "faithfulness" in scores and scores["faithfulness"] is not None:
            faithfulness_scores.append(scores["faithfulness"])
        if "answer_relevancy" in scores and scores["answer_relevancy"] is not None:
            relevancy_scores.append(scores["answer_relevancy"])
        if "context_recall" in scores and scores["context_recall"] is not None:
            recall_scores.append(scores["context_recall"])
        if "context_precision" in scores and scores["context_precision"] is not None:
            precision_scores.append(scores["context_precision"])

    def _avg(values: list[float]) -> Optional[float]:
        return round(sum(values) / len(values), 4) if values else None

    return EvalReport(
        collection_id=collection_id,
        message_count=len(messages),
        avg_faithfulness=_avg(faithfulness_scores),
        avg_answer_relevancy=_avg(relevancy_scores),
        avg_context_recall=_avg(recall_scores),
        avg_context_precision=_avg(precision_scores),
    )