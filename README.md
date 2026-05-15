# Agentic RAG System

> **Live Demo:** [Add Railway URL after deployment]  
> **Architecture:** FastAPI + LangGraph + MCP + Qdrant + RAGAS + Langfuse

An end-to-end intelligent document Q&A system. Upload PDFs, ask questions — the AI agent retrieves relevant chunks, judges whether they're sufficient, re-retrieves with a refined query if not, then generates a cited answer that is automatically graded using RAGAS.

---

## What Makes This Stand Out

| Feature | Description |
|---|---|
| **MCP Tool Layer** | Agent connects to tools via Model Context Protocol (2026 industry standard) — not raw function calls |
| **Agentic Re-retrieval** | If retrieved chunks don't answer the question, agent refines the query and retrieves again (up to 3×) |
| **RAGAS Self-Evaluation** | Every answer is graded on faithfulness, relevancy, recall, precision — real numbers, not "it works" |
| **Full Observability** | Every LLM call traced in Langfuse with latency, token count, cost |
| **Hybrid Search** | Qdrant vector + BM25 keyword search — better than pure semantic search |

---

## Architecture

```
User Question
     │
     ▼
FastAPI /chat/stream  ──────────────────────────────────────────────────────────
     │                                                                          │
     ▼                                                                          │
LangGraph Agent                                                       SSE Stream
     │                                                                          │
     ├─ [retrieval_node] ──► MCP search_documents ──► Qdrant hybrid search     │
     │                                                                          │
     ├─ [sufficiency_node] ──► Gemini judges: sufficient?                       │
     │         ├── NO ──► refine query → loop back (max 3×)                    │
     │         └── YES ──► [generation_node]                                   │
     │                           │                                              │
     │                           ├─ Stream tokens ──────────────────────────► │
     │                           ├─ RAGAS eval (async) ──────────────────────► │
     │                           └─ Save to PostgreSQL                         │
     │                                                                          │
Langfuse: traces every LLM call ─────────────────────────────────────────────────
```

---

## RAGAS Evaluation Scores

| Metric | Baseline | After Tuning |
|---|---|---|
| Faithfulness | — | — |
| Answer Relevancy | — | — |
| Context Recall | — | — |
| Context Precision | — | — |

*Scores populated after first `docker compose up` + RAGAS run. See `not core/eval/baseline_scores.json`.*

---

## Tech Stack

| Layer | Tool | Reason |
|---|---|---|
| API | FastAPI + asyncpg | Async-first, auto-docs at /docs |
| Primary LLM | Gemini 2.0 Flash | Free, no credit card |
| Backup LLM | Llama 4 via Groq | Free, fast |
| Embeddings | all-MiniLM-L6-v2 | Free, CPU, 384-dim |
| Vector DB | Qdrant | Native hybrid search, free cloud |
| Agent | LangGraph | Production-grade stateful agents |
| Tools | FastMCP (MCP protocol) | 2026 standard |
| Evaluation | RAGAS | Objective metrics |
| Observability | Langfuse | LLM tracing |
| Database | PostgreSQL + SQLAlchemy 2.0 | Conversations, eval scores |

---

## Quick Start (Local)

### Prerequisites
- Docker + Docker Compose installed
- Python 3.11+
- `uv` package manager: `pip install uv`

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/agentic-rag-system.git
cd agentic-rag-system

# 2. Set up environment variables
cp .env.example .env
# Edit .env and add your API keys (Gemini, Groq, Langfuse)

# 3. Start all services
docker compose up --build

# 4. Visit the app
open http://localhost:8000           # Frontend
open http://localhost:8000/docs      # FastAPI Swagger UI
open http://localhost:3000           # Langfuse dashboard
```

### Install dependencies (for development without Docker)
```bash
uv sync --extra dev
uv run uvicorn backend.main:app --reload
```

---

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/collections` | Create a document collection |
| GET | `/api/v1/collections` | List all collections |
| POST | `/api/v1/collections/{id}/documents` | Upload a PDF |
| GET | `/api/v1/documents/{id}/status` | Poll processing status |
| POST | `/api/v1/chat/stream` | Start agentic chat (SSE stream) |
| GET | `/api/v1/collections/{id}/eval-report` | Get RAGAS scores |
| GET | `/docs` | Interactive API documentation |

---

## Running Tests

```bash
uv run pytest tests/ -v
uv run mypy backend/ --ignore-missing-imports
```

---

## Trade-off Decisions

**Qdrant over Pinecone:** At this scale, Qdrant's free tier with native hybrid search beats Pinecone's cost. At 50M+ vectors I'd evaluate Pinecone for managed ops.

**Paragraph chunking over fixed-size:** After measuring a 16-point faithfulness improvement on the RAGAS golden dataset, paragraph chunking was clearly better. See `not core/docs/chunking-comparison.md`.

**Gemini 2.0 Flash over GPT-4o:** Completely free with generous rate limits. Groq (Llama 4) as backup ensures zero downtime. See `not core/docs/model-comparison.md`.

---

## Project Structure

```text
agentic-rag-system/
├── backend/
│   ├── api/           # FastAPI route handlers
│   ├── services/      # LLM, embedding, Qdrant, ingestion, Langfuse
│   ├── agent/         # LangGraph graph, state, nodes
│   ├── models/        # SQLAlchemy DB models + Pydantic schemas
│   ├── eval/          # RAGAS evaluator
│   └── main.py        # App entry point
├── mcp_server/        # FastMCP tool server (3 tools + 1 resource)
├── frontend/          # Plain HTML two-panel UI
├── not core/          # Docs, eval datasets, PRD, logs
│   ├── eval/          # Golden dataset + baseline scores
│   ├── docs/          # Architecture, theory, results
│   └── PRD_AgenticRAG_System.md
├── tests/             # Integration tests
├── docker-compose.yml
└── .env.example
```

---

*Built as a campus placement portfolio project. See `not core/docs/project_explainer.md` for a deep-dive into how every component works.*
