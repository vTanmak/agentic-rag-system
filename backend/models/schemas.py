import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    PROCESSING = "processing"
    DONE       = "done"
    FAILED     = "failed"

class MessageRole(str, Enum):
    USER      = "user"
    ASSISTANT = "assistant"

class SSEEventType(str, Enum):
    TOKEN     = "token"
    RETRIEVAL = "retrieval"
    SOURCES   = "sources"
    EVAL      = "eval"
    DONE      = "done"

class CollectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)

class CollectionResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}

class CollectionListResponse(BaseModel):
    collections: list[CollectionResponse]
    total: int

class DocumentUploadResponse(BaseModel):
    document_id: uuid.UUID
    filename: str
    status: DocumentStatus = DocumentStatus.PROCESSING
    message: str = "Document queued. Poll /status for updates."

class DocumentStatusResponse(BaseModel):
    document_id: uuid.UUID
    filename: str
    status: DocumentStatus
    chunk_count: Optional[int] = None
    error_message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}

class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    collection_id: uuid.UUID
    session_id: Optional[uuid.UUID] = None
    max_retries: int = Field(default=3, ge=1, le=5)

class SourceChunk(BaseModel):
    source: str
    page: int
    chunk_index: int
    text_preview: str
    score: float

class RAGASScores(BaseModel):
    faithfulness: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    answer_relevancy: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    context_recall: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    context_precision: Optional[float] = Field(default=None, ge=0.0, le=1.0)

class TokenEvent(BaseModel):
    type: SSEEventType = SSEEventType.TOKEN
    content: str

class RetrievalEvent(BaseModel):
    type: SSEEventType = SSEEventType.RETRIEVAL
    iteration: int

class SourcesEvent(BaseModel):
    type: SSEEventType = SSEEventType.SOURCES
    data: list[SourceChunk]

class EvalEvent(BaseModel):
    type: SSEEventType = SSEEventType.EVAL
    scores: RAGASScores

class DoneEvent(BaseModel):
    type: SSEEventType = SSEEventType.DONE
    session_id: uuid.UUID
    trace_id: Optional[str] = None

class EvalReport(BaseModel):
    collection_id: uuid.UUID
    message_count: int
    avg_faithfulness: Optional[float] = None
    avg_answer_relevancy: Optional[float] = None
    avg_context_recall: Optional[float] = None
    avg_context_precision: Optional[float] = None

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"

class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None