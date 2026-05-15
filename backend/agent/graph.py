import logging

from langgraph.graph import END, START, StateGraph
from backend.agent.nodes import (
    MAX_RETRIEVAL_ATTEMPTS,
    generation_node,
    retrieval_node,
    sufficiency_node,
)
from backend.agent.state import AgentState

logger = logging.getLogger(__name__)

def _should_continue_retrieval(state: AgentState) -> str:
    is_sufficient = state.get("is_sufficient", False)
    retrieval_count = state.get("retrieval_count", 0)

    if is_sufficient:
        logger.info("[router] Chunks sufficient → generating answer")
        return "generate"

    if retrieval_count >= MAX_RETRIEVAL_ATTEMPTS:
        logger.info(f"[router] Max retries ({MAX_RETRIEVAL_ATTEMPTS}) reached → generating best-effort answer")
        return "generate"

    logger.info(f"[router] Not sufficient, attempt {retrieval_count}/{MAX_RETRIEVAL_ATTEMPTS} → re-retrieving")
    return "retrieve_again"

def build_agent_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("retrieval", retrieval_node)
    graph.add_node("sufficiency", sufficiency_node)
    graph.add_node("generation", generation_node)

    graph.add_edge(START, "retrieval")

    graph.add_edge("retrieval", "sufficiency")

    graph.add_conditional_edges(
        "sufficiency",
        _should_continue_retrieval,
        {
            "generate": "generation",
            "retrieve_again": "retrieval",
        },
    )

    graph.add_edge("generation", END)

    compiled = graph.compile()
    logger.info("LangGraph agent graph compiled successfully")
    return compiled


agent_graph = build_agent_graph()