# Product Requirements Document
## Agentic RAG System with MCP + Self-Evaluation
**Version:** 1.0 | **Author:** Tanishq | **Target:** Campus Placement Portfolio Project

---

## 1. Project Summary

**What it is:** A web application where users upload PDF documents, then ask questions about them. Unlike a simple chatbot, the system uses an AI agent that decides whether to search again if its first retrieval wasn't good enough — and then grades its own answers automatically.

**Why it matters (your pitch):** Enterprises can't query their own knowledge bases reliably. Keyword search misses meaning. Generic LLMs hallucinate without your data. This system solves both — agentic retrieval + self-evaluation + full observability.

**What makes it stand out:**
- Uses MCP (the 2026 industry standard) for tool connections — almost no student project does this
- Agent re-retrieves if first search is insufficient (agentic loop)
- RAGAS evaluation on every answer — real numbers, not "it works well"
- Traces every request end-to-end with Langfuse
- Deployed publicly, not localhost

---

## 2. Tech Stack (What You're Actually Using)

| Layer | Tool | Why |
|---|---|---|
| API Server | FastAPI + asyncpg | Async-first, auto-docs at /docs |
| Primary LLM | Gemini 2.0 Flash | Free, no card needed |
| Backup LLM | Llama 4 via Groq | Free, fast inference |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) | Free, runs locally on CPU |
| Vector DB | Qdrant (Docker / free cloud) | Best free option, hybrid search built-in |
| Agent Framework | LangGraph | Production-grade stateful agents |
| Data Validation | Pydantic v2 | Used everywhere — FastAPI, LangGraph state |
| Tool Protocol | MCP via FastMCP | 2026 standard, Anthropic created it |
| Evaluation | RAGAS (Gemini as judge) | Completely free, measures quality objectively |
| Observability | Langfuse (self-hosted Docker) | Traces every LLM call with cost + latency |
| Database | PostgreSQL + SQLAlchemy 2.0 | Stores conversations, documents, eval scores |
| Package Manager | uv | Faster than pip, now industry standard |
| Frontend | Plain HTML + SSE (or Next.js) | Keep it simple — 2 days max |
| Deployment | Railway free tier | Public URL before you apply |
| CI/CD | GitHub Actions | Auto-test + auto-deploy on push |

---

## 3. Core Features (What the System Does)

### Feature 1 — Document Ingestion
User uploads a PDF. The system processes it in the background and notifies when ready.

**Inputs:** PDF file, collection name  
**Outputs:** Document stored with chunks embedded in Qdrant, status trackable via API

**What happens internally:**
1. PDF text extracted with `pypdf`
2. Text split into paragraph chunks (~400 tokens, 50 token overlap)
3. Each chunk embedded using `all-MiniLM-L6-v2` locally
4. Chunks stored in Qdrant with metadata: source, page number, chunk index, text preview
5. Document record stored in PostgreSQL with status (processing → done)

**API endpoints:**
- `POST /api/v1/collections/{id}/documents` — upload file, returns immediately with `{document_id, status: "processing"}`
- `GET /api/v1/documents/{id}/status` — poll for `{status, chunk_count, error_message}`

---

### Feature 2 — Agentic RAG Chat (Core Feature)
User asks a question. The agent retrieves relevant chunks, judges if they're sufficient, re-retrieves with a better query if not, then generates a cited answer — streamed in real time.

**Inputs:** Question text, collection ID, optional session ID  
**Outputs:** Streamed answer with cited sources, retrieval count, RAGAS evaluation scores

**The Agent Loop (LangGraph):**

```
User Question
     │
     ▼
[retrieval_node] ──── calls MCP search_documents tool ────► Qdrant hybrid search
     │
     ▼
[sufficiency_node] ── Gemini judges: sufficient? ─────────► SufficiencyResult(sufficient, reason, refined_query)
     │
     ├── YES or retries ≥ 3 ──► [generation_node] ──► Cited answer streamed back
     │
     └── NO ──────────────────► loop back to retrieval_node with refined_query
```

**LangGraph State (TypedDict):**
```python
{
  "query": str,
  "collection_id": str,
  "retrieved_chunks": list,
  "retrieval_count": int,       # max 3 retries
  "answer": str,
  "sources": list,
  "is_sufficient": bool
}
```

**SSE Stream events (in order):**
```
{type: "token", content: "..."}         # Answer tokens, real-time
{type: "retrieval", iteration: 2}       # Shows agent re-retrieved
{type: "sources", data: [...]}          # Source chunks after generation
{type: "done"}
```

---

### Feature 3 — MCP Tool Layer
The agent uses tools via MCP protocol — not raw function calls. This is the key differentiator.

**MCP Server (FastMCP) exposes 3 tools + 1 resource:**

| Tool/Resource | What it does | Backend |
|---|---|---|
| `search_documents(query, collection_id, top_k)` | Hybrid vector + keyword search | Qdrant |
| `get_document_metadata(doc_id)` | Fetch document info | PostgreSQL |
| `web_search(query)` | Search the web | DuckDuckGo (free, no key) |
| `@resource: collection_stats` | Doc count, chunk count, last updated | PostgreSQL |

**Input validation on every tool:**
- Empty strings → clear error, no crash
- Very long inputs (5000+ chars) → reject with message
- Invalid UUIDs → reject with message

**Run locally:** `fastmcp run server.py --transport stdio`  
**Deployed:** `fastmcp run server.py --transport sse`

---

### Feature 4 — RAGAS Self-Evaluation
The system grades its own answers on every chat response. Runs asynchronously — doesn't delay the stream.

**4 RAGAS metrics (Gemini 2.0 Flash as free judge):**

| Metric | What it measures | Target |
|---|---|---|
| `faithfulness` | Is the answer grounded in retrieved context? | > 0.80 |
| `answer_relevancy` | Does the answer actually address the question? | > 0.75 |
| `context_recall` | Did retrieval find the relevant chunks? | > 0.70 |
| `context_precision` | Are retrieved chunks actually used in the answer? | > 0.70 |

**Golden dataset:** 25 hand-crafted hard question-answer-context triplets stored in `/eval/golden_dataset.json`. "Hard" means multi-hop reasoning, requires synthesizing two sections, or should correctly refuse (no hallucination).

**How it feeds back:**
- Scores saved to PostgreSQL per message (in `eval_scores_json` column)
- `GET /api/v1/collections/{id}/eval-report` returns aggregate scores for last 50 messages
- Frontend shows eval badges below each answer
- Before/after score deltas documented in `/docs/eval-results.md`

---

### Feature 5 — Observability with Langfuse
Every LLM call is traced. You can show any trace live during an interview.

**What gets recorded per request:**
- Input prompt + output
- Latency (time to first token, total)
- Token count
- Estimated cost
- Unique `trace_id` per chat request

**Setup:** Langfuse self-hosted via Docker (free), or Langfuse cloud free tier. Every LLM call emits a span tagged with the trace_id.

---

### Feature 6 — Frontend
Keep it simple. 2 days maximum. Backend depth is your differentiator.

**Layout:** Two-panel
- Left panel: upload PDF, select/create collection, see processing status
- Right panel: chat interface

**Chat panel shows:**
- Streaming tokens in real-time (via EventSource)
- "Retrieved 2×" indicator when agent looped
- Source chips below the answer (clickable, shows chunk text)
- Eval badges (e.g., "Faithfulness 0.87")
- File upload: drag-and-drop + progress bar

---

## 4. Data Models

### PostgreSQL Tables

**Collection**
```
id (UUID), name (str), created_at (timestamp)
```

**Document**
```
id (UUID), collection_id (FK), filename (str),
chunk_count (int), status (enum: processing/done/failed),
error_message (str nullable), created_at (timestamp)
```

**ConversationSession**
```
id (UUID), collection_id (FK), created_at (timestamp)
```

**Message**
```
id (UUID), session_id (FK), role (user/assistant),
content (text), sources_json (JSONB),
eval_scores_json (JSONB), trace_id (str), created_at (timestamp)
```

### Qdrant Collection Structure

Each chunk stored as a vector with this payload:
```json
{
  "source": "filename.pdf",
  "collection_id": "uuid",
  "page": 3,
  "chunk_index": 12,
  "text_preview": "first 100 chars...",
  "text": "full chunk text"
}
```

---

## 5. API Reference

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/collections` | Create a new collection |
| GET | `/api/v1/collections` | List all collections |
| POST | `/api/v1/collections/{id}/documents` | Upload a PDF (background processing) |
| GET | `/api/v1/documents/{id}/status` | Poll processing status |
| POST | `/api/v1/chat/stream` | Start a chat (returns SSE stream) |
| GET | `/api/v1/collections/{id}/eval-report` | Get aggregate RAGAS scores |
| GET | `/docs` | FastAPI auto-generated docs (show in interview) |

---

## 6. Folder Structure

```
ai-rag-system/
├── backend/
│   ├── api/           # FastAPI routes
│   ├── services/      # LLM client, embedding service, Qdrant service
│   ├── agent/         # LangGraph graph definition
│   ├── models/        # SQLAlchemy + Pydantic models
│   ├── eval/          # RAGAS evaluator
│   └── main.py
├── mcp_server/
│   └── server.py      # FastMCP tool definitions
├── frontend/
│   └── index.html     # Two-panel UI
├── eval/
│   ├── golden_dataset.json
│   └── baseline_scores.json
├── docs/
│   ├── architecture.md        # Mermaid diagram — draw BEFORE coding
│   ├── llm-theory.md          # Your 5 LLM theory answers
│   ├── agent-graph.png        # LangGraph diagram export
│   ├── chunking-comparison.md # Results from Week 5 experiment
│   ├── eval-results.md        # Before/after RAGAS deltas
│   └── model-comparison.md   # GPT-4o-mini vs Gemini vs Groq comparison
├── tests/
│   ├── test_ingestion.py
│   ├── test_agent.py
│   └── test_mcp.py
├── docker-compose.yml         # FastAPI + PostgreSQL + Qdrant + Langfuse
├── .env.example               # Never commit real keys
├── .github/workflows/ci.yml   # pytest → mypy → deploy
└── README.md
```

---

## 7. What You Build Phase by Phase

| Phase | Weeks | What gets built |
|---|---|---|
| Foundation | 1–3 | Python models, FastAPI server, PostgreSQL, Docker setup |
| LLM Layer | 4 | Multi-provider LLM client (Gemini + Groq + OpenAI wrapper) |
| Retrieval | 5 | Ingestion pipeline, Qdrant setup, chunking experiments |
| Agentic RAG | 6 | Self-RAG loop, HyDE, cross-encoder reranking |
| MCP Server | 7 | FastMCP with 3 tools + resource, input validation |
| Agent + LangGraph | 8 | LangGraph state machine, PydanticAI structured outputs |
| Eval + Streaming | 9 | RAGAS golden dataset, Langfuse traces, SSE endpoint |
| Full Project | 10 | Architecture diagram, full integration, CI/CD |
| Deploy | 11 | Railway deployment, frontend, public URL |
| Interview Prep | 12 | Architecture decision record, video walkthrough, pitch |

---

## 8. Interview Talking Points (Built into the Project)

**The three things no other student project has — lead with these:**

**MCP Tool Layer**
"The agent doesn't use raw function calling. It connects to tools via MCP — the Model Context Protocol created by Anthropic, now adopted by OpenAI, Google, and Microsoft. It's the 2026 standard. Every tool call goes through the MCP server."

**Agentic Re-retrieval**
"Most RAG projects retrieve once and generate. Mine checks sufficiency. If the retrieved chunks don't answer the question, the agent generates a refined query and retrieves again — up to 3 times. I tested on 10 queries where one retrieval genuinely wasn't enough."

**RAGAS Self-Evaluation**
"Faithfulness went from 0.71 to 0.87 when I switched from fixed-size to paragraph chunking. That's not an opinion — it's measured. The system grades itself on every answer using RAGAS with Gemini as the judge."

**Trade-off you own:**
"I chose Qdrant over Pinecone because at this scale Qdrant's free tier with native hybrid search beats Pinecone's cost. At 50M+ vectors I'd evaluate Pinecone for managed ops. I chose paragraph chunking over fixed-size after measuring a 16-point faithfulness improvement."

---

## 9. Definition of Done (Before Applying)

- [ ] `docker compose up` starts the full stack on a clean machine — no errors
- [ ] PDF upload works end-to-end (upload → processing → done → searchable)
- [ ] Agentic loop re-retrieves at least once on a multi-hop question
- [ ] SSE stream delivers: tokens, retrieval indicator, sources, eval scores, done
- [ ] RAGAS baseline run on golden dataset, scores saved in `/eval/baseline_scores.json`
- [ ] Langfuse dashboard shows traces for all LLM calls
- [ ] MCP server: all 3 tools tested, input validation tested (empty, long, invalid UUID)
- [ ] 12 integration tests passing in CI (GitHub Actions: pytest → mypy → pass)
- [ ] Deployed on Railway with public URL
- [ ] Screen recording: upload PDF → multi-hop question → show re-retrieval → Langfuse trace → RAGAS scores (6 minutes max, YouTube unlisted)
- [ ] README: live URL, architecture diagram, RAGAS scores table, trade-off reasoning
- [ ] 90-second pitch practiced until it sounds like a conversation, not a script
- [ ] No hardcoded API keys anywhere (`.env` + `.gitignore` from day one)

---

## 10. What NOT to Build (Scope Limits)

- No user authentication / login system
- No multi-tenancy
- No fine-tuning of any model
- No Graph RAG (too complex, no placement payoff)
- No Kubernetes / Terraform
- Frontend: 2 days max — no complex state management, no animations, no design system
- No A/B testing infrastructure

---

*Draw the architecture diagram in `/docs/architecture.md` before writing a single line of code. A messy diagram means a messy architecture — fix it on paper first.*
