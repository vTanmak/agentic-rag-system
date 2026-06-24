import pytest
import uuid
from unittest.mock import AsyncMock, patch

def _make_state(**overrides):
    # create a fake langgraph state
    base = {
        "query": "What is the main topic?",
        "collection_id": str(uuid.uuid4()),
        "current_query": "What is the main topic?",
        "retrieved_chunks": [],
        "retrieval_count": 0,
        "is_sufficient": False,
        "refined_query": None,
        "answer": "",
        "sources": [],
        "trace_id": "test-trace-123",
        "sse_events": [],
    }
    base.update(overrides)
    return base

@pytest.mark.asyncio
async def test_retrieval_node_increments_count(mock_embedding, mock_qdrant):
    # test that search counter goes up
    with (
        patch("backend.agent.nodes.embedding_service", mock_embedding),
        patch("backend.agent.nodes.qdrant_service", mock_qdrant),
    ):
        from backend.agent.nodes import retrieval_node
        state = _make_state(retrieval_count=0)
        result = await retrieval_node(state)

    assert result["retrieval_count"] == 1

@pytest.mark.asyncio
async def test_retrieval_node_appends_chunks(mock_embedding, mock_qdrant):
    # test new search chunks are added
    with (
        patch("backend.agent.nodes.embedding_service", mock_embedding),
        patch("backend.agent.nodes.qdrant_service", mock_qdrant),
    ):
        from backend.agent.nodes import retrieval_node
        state = _make_state(retrieved_chunks=[{"text": "old chunk", "source": "a.pdf", "chunk_index": 0}])
        result = await retrieval_node(state)

    assert len(result["retrieved_chunks"]) > 1

@pytest.mark.asyncio
async def test_retrieval_node_emits_sse_event(mock_embedding, mock_qdrant):
    # test frontend gets the loading event
    with (
        patch("backend.agent.nodes.embedding_service", mock_embedding),
        patch("backend.agent.nodes.qdrant_service", mock_qdrant),
    ):
        from backend.agent.nodes import retrieval_node
        state = _make_state()
        result = await retrieval_node(state)

    retrieval_events = [e for e in result["sse_events"] if e["type"] == "retrieval"]
    assert len(retrieval_events) == 1

@pytest.mark.asyncio
async def test_sufficiency_node_parses_true():
    # test the ai saying yes
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = '{"sufficient": true, "reason": "All info present", "refined_query": null}'

    with (
        patch("backend.agent.nodes.llm_client", mock_llm),
        patch("backend.agent.nodes.langfuse_client"),
    ):
        from backend.agent.nodes import sufficiency_node
        state = _make_state(retrieved_chunks=[{"source": "a.pdf", "page": 1, "text": "Some context"}])
        result = await sufficiency_node(state)

    assert result["is_sufficient"] is True

@pytest.mark.asyncio
async def test_sufficiency_node_parses_false_with_refined_query():
    # test the ai saying no and giving a new search
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = '{"sufficient": false, "reason": "Missing details", "refined_query": "more specific query"}'

    with (
        patch("backend.agent.nodes.llm_client", mock_llm),
        patch("backend.agent.nodes.langfuse_client"),
    ):
        from backend.agent.nodes import sufficiency_node
        state = _make_state()
        result = await sufficiency_node(state)

    assert result["is_sufficient"] is False
    assert result["refined_query"] == "more specific query"

@pytest.mark.asyncio
async def test_sufficiency_node_fails_open_on_parse_error():
    # test that bad json doesn't crash everything
    mock_llm = AsyncMock()
    mock_llm.generate.return_value = "not valid json at all"

    with (
        patch("backend.agent.nodes.llm_client", mock_llm),
        patch("backend.agent.nodes.langfuse_client"),
    ):
        from backend.agent.nodes import sufficiency_node
        state = _make_state()
        result = await sufficiency_node(state)

    assert result["is_sufficient"] is True

def test_routing_goes_to_generate_when_sufficient():
    # agent should answer if context is good
    from backend.agent.graph import _should_continue_retrieval
    state = _make_state(is_sufficient=True, retrieval_count=1)
    assert _should_continue_retrieval(state) == "generate"

def test_routing_loops_when_not_sufficient_and_retries_remaining():
    # agent should loop if context is bad
    from backend.agent.graph import _should_continue_retrieval
    state = _make_state(is_sufficient=False, retrieval_count=1)
    assert _should_continue_retrieval(state) == "retrieve_again"

def test_routing_forces_generate_at_max_retries():
    # agent should eventually give up and answer
    from backend.agent.graph import _should_continue_retrieval, MAX_RETRIEVAL_ATTEMPTS
    state = _make_state(is_sufficient=False, retrieval_count=MAX_RETRIEVAL_ATTEMPTS)
    assert _should_continue_retrieval(state) == "generate"

@pytest.mark.asyncio
async def test_generation_node_produces_answer():
    # test ai answering the question
    mock_llm = AsyncMock()
    async def fake_stream(*args, **kwargs):
        for token in ["The ", "answer ", "is ", "here."]:
            yield token
    mock_llm.stream = fake_stream

    with (
        patch("backend.agent.nodes.llm_client", mock_llm),
        patch("backend.agent.nodes.langfuse_client"),
    ):
        from backend.agent.nodes import generation_node
        state = _make_state(
            retrieved_chunks=[{
                "source": "a.pdf", "page": 1, "chunk_index": 0,
                "text": "Relevant information.", "text_preview": "Relevant...", "score": 0.9
            }]
        )
        result = await generation_node(state)

    assert result["answer"] == "The answer is here."
    assert len(result["sources"]) == 1
