# LLM Theory — 5 Interview Questions

*Solid, concise answers to the most common LLM/RAG interview questions.*
*Practice saying these out loud until they sound natural, not memorized.*

---

## Q1: What is RAG and why is it better than just using an LLM?

**Answer:**

RAG stands for Retrieval-Augmented Generation. Instead of relying only on what the LLM learned during training, RAG first retrieves relevant documents from your own knowledge base, then passes them as context to the LLM to generate an answer.

The key benefits over a plain LLM:
- **No hallucination on your data** — the LLM can only cite what you retrieved. If it's not in the context, it should say "I don't know."
- **Up-to-date** — the knowledge base can be updated without retraining the model.
- **Private data** — your internal documents never need to be sent to a third party for fine-tuning.

The trade-off: RAG is only as good as your retrieval. If you retrieve the wrong chunks, the answer will be wrong even though the LLM is working correctly. This is exactly why I added a sufficiency check — the agent judges whether the retrieved context is actually useful before generating.

---

## Q2: What is the difference between semantic search and keyword search? Why use hybrid?

**Answer:**

**Keyword search (BM25):** Finds documents that contain the exact words in your query. Very precise for exact matches, but misses synonyms. Searching "automobile" won't find "car."

**Semantic search (vector/embedding):** Converts text into a vector of numbers that captures meaning. Similar meaning → similar vectors → high cosine similarity score. "Car" and "automobile" land near each other in vector space.

**Why hybrid?** Each has failure cases:
- Pure semantic: might return a slightly-off-topic chunk that happens to be semantically similar, missing an exact keyword match that's clearly relevant.
- Pure keyword: misses meaning-based queries entirely.

Hybrid search (what Qdrant supports natively) does both and merges the results — you get the precision of keyword search plus the semantic understanding of vector search. In practice, faithfulness and context recall both improve.

---

## Q3: What causes LLM hallucination, and how does this project address it?

**Answer:**

LLMs hallucinate because they're trained to produce plausible-sounding completions, not verified facts. When they don't know something, they "fill in the gap" with confident-sounding but invented content.

This project addresses it at three levels:

1. **Retrieval grounding:** The system prompt tells the LLM: "Answer ONLY using the provided context. If the context doesn't contain the answer, say so." This anchors the output to real retrieved text.

2. **Agentic re-retrieval:** If the first retrieval doesn't find good context, the agent retrieves again with a better query instead of trying to generate with insufficient context (which would force the LLM to hallucinate).

3. **RAGAS faithfulness score:** After every answer, we measure whether each statement in the answer is traceable to the retrieved chunks. A faithfulness score below 0.7 tells me the answer is likely hallucinated. I can see this per-message in the UI and in aggregate in the eval report.

---

## Q4: What is an embedding model and why do we use all-MiniLM-L6-v2?

**Answer:**

An embedding model converts text into a dense vector — a list of floating-point numbers (384 in our case) where the geometry encodes meaning. Texts with similar meaning cluster together in this high-dimensional space.

**Why all-MiniLM-L6-v2 specifically:**
- **Free and local:** runs on CPU, no API cost, no rate limits, no internet needed
- **Fast:** 384 dimensions is small enough for real-time search
- **Good quality:** strong benchmark performance for a lightweight model
- **No dependency:** the model downloads once (~90MB) and then runs locally forever

The trade-off vs OpenAI's text-embedding-3-large: OpenAI's model scores higher on benchmarks, but costs money per query and has rate limits. At this scale (personal knowledge base, <10k documents), all-MiniLM-L6-v2 is more than sufficient. At enterprise scale with millions of queries, the benchmark improvement might justify the cost.

---

## Q5: What is MCP and why did you use it instead of regular function calling?

**Answer:**

MCP (Model Context Protocol) is an open protocol created by Anthropic that standardizes how AI agents connect to external tools and data sources. OpenAI, Google, and Microsoft all adopted it in 2025-2026.

The analogy: before USB, every device had a different plug. MCP is the "USB standard for AI tools" — any MCP-compatible agent can use any MCP server without custom glue code.

**Why not just use regular Python function calling?**

With direct function calls, the agent code is tightly coupled to the tool implementation. If I want to run the tools on a separate server, or expose them to a different agent framework, I'd need to rewrite the integration.

With MCP:
- The tools run as a separate service (the MCP server)
- The agent connects to them over a standard protocol (stdio or SSE)
- Any MCP-compatible agent (LangGraph, Claude Desktop, Cursor, etc.) can use the same tools
- In production, the MCP server can be scaled independently

For placements: MCP is the 2026 industry direction. Anthropic, OpenAI, and Google are all building their agent infrastructure around it. Having it on your resume and being able to explain the protocol distinction shows you're following where the industry is going, not just the tutorials.
