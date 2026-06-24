import asyncio
import json
import logging
import uuid
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.agent.graph import agent_graph
from backend.eval.evaluator import evaluate_response, save_eval_scores
from backend.models.database import Collection,ConversationSession,Message,async_session_factory,get_db_session
from backend.models.schemas import ChatRequest
from backend.services.langfuse_client import langfuse_client
from backend.api.deps import get_user_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["Chat"])

@router.post("/stream")
async def chat_stream(
    body: ChatRequest,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db_session)):
    session_id = body.session_id
    if session_id is None:
        new_session = ConversationSession(collection_id=body.collection_id, user_id=user_id)
        db.add(new_session)
        await db.commit()
        await db.refresh(new_session)
        session_id = new_session.id
    else:
        existing_session = await db.get(ConversationSession, session_id)
        if not existing_session or existing_session.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )

    user_message = Message(
        session_id=session_id,
        role="user",
        content=body.question,
    )
    db.add(user_message)
    await db.commit()
    await db.refresh(user_message)

    trace_id = langfuse_client.create_trace(
        name="chat_request",
        user_id="anonymous",
    )

    initial_state = {
        "query": body.question,
        "collection_id": str(body.collection_id),
        "current_query": body.question,
        "retrieved_chunks": [],
        "retrieval_count": 0,
        "is_sufficient": False,
        "refined_query": None,
        "answer": "",
        "sources": [],
        "trace_id": trace_id,
        "sse_events": [],
    }

    return StreamingResponse(
        _generate_sse_stream(
            initial_state=initial_state,
            session_id=session_id,
            trace_id=trace_id,
            max_retries=body.max_retries,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

async def _generate_sse_stream(
    initial_state: dict,
    session_id: uuid.UUID,
    trace_id: str,
    max_retries: int,
) -> AsyncGenerator[str, None]:
    final_state = {}
    assistant_message_id = None

    try:
        final_state = await agent_graph.ainvoke(initial_state)

        for event in final_state.get("sse_events", []):
            yield _format_sse(event)
            await asyncio.sleep(0)

        async with async_session_factory() as db:
            assistant_message = Message(
                session_id=session_id,
                role="assistant",
                content=final_state.get("answer", ""),
                sources_json=final_state.get("sources", []),
                trace_id=trace_id,
            )
            db.add(assistant_message)
            await db.flush()
            assistant_message_id = assistant_message.id
            await db.commit()

        langfuse_client.log_llm_call(
            trace_id=trace_id,
            step_name="agent_graph_execution",
            input_text=initial_state["query"],
            output_text=final_state.get("answer", ""),
            model="agent-graph",
        )

        # Update the root trace so the Langfuse table shows the actual question and answer
        if langfuse_client._enabled and langfuse_client._client:
            langfuse_client._client.trace(
                id=trace_id,
                input=initial_state["query"],
                output=final_state.get("answer", "")
            )

        yield _format_sse({"type": "generation_done"})

        if final_state.get("answer") and final_state.get("retrieved_chunks"):
            context_texts = [c["text"] for c in final_state.get("retrieved_chunks", [])]
            eval_scores = await evaluate_response(
                question=initial_state["query"],
                answer=final_state["answer"],
                contexts=context_texts,
            )

            yield _format_sse({
                "type": "eval",
                "scores": eval_scores.model_dump(exclude_none=True),
            })

            if assistant_message_id:
                asyncio.create_task(
                    _save_scores_background(assistant_message_id, eval_scores, trace_id)
                )

    except Exception as e:
        logger.error(f"Chat stream error: {e}")
        yield _format_sse({"type": "error", "message": str(e)})

    finally:
        yield _format_sse({
            "type": "done",
            "session_id": str(session_id),
            "trace_id": trace_id,
        })

        langfuse_client.flush()


async def _save_scores_background(message_id, scores, trace_id: str) -> None:
    async with async_session_factory() as db:
        await save_eval_scores(db, message_id, scores)
    
    if scores.faithfulness is not None:
        langfuse_client.log_score(trace_id, "faithfulness", scores.faithfulness)
    if scores.answer_relevancy is not None:
        langfuse_client.log_score(trace_id, "answer_relevancy", scores.answer_relevancy)
    
    langfuse_client.flush()


def _format_sse(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"

@router.get("/collections/{collection_id}/sessions")
async def list_collection_sessions(
    collection_id: uuid.UUID,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    collection = await db.get(Collection, collection_id)
    if not collection or collection.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Collection {collection_id} not found",
        )

    result = await db.execute(
        select(ConversationSession)
        .where(ConversationSession.collection_id == collection_id)
        .order_by(ConversationSession.created_at.desc())
    )
    sessions = result.scalars().all()
    return {
        "sessions": [
            {
                "id": str(s.id),
                "collection_id": str(s.collection_id),
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in sessions
        ]
    }

@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: uuid.UUID,
    user_id: str = Depends(get_user_id),
    db: AsyncSession = Depends(get_db_session),
):
    session = await db.get(ConversationSession, session_id)
    if not session or session.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    )
    messages = result.scalars().all()
    return {
        "messages": [
            {
                "id": str(msg.id),
                "role": msg.role,
                "content": msg.content,
                "sources": msg.sources_json or [],
                "eval_scores": msg.eval_scores_json or {},
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
            for msg in messages
        ]
    }