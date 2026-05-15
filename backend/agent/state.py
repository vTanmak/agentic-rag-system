from typing import TypedDict, Optional

class AgentState(TypedDict):
    query: str
    collection_id: str
    current_query: str
    retrieved_chunks: list[dict]
    retrieval_count: int
    is_sufficient: bool
    refined_query: Optional[str]
    answer: str
    sources: list[dict]
    trace_id: str
    sse_events: list[dict]