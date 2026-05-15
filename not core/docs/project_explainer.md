# Project Explainer — Agentic RAG System

*Your deep-dive reference. Explains every file, every concept, and how everything connects.*
*Read this when you want to understand why the code is structured the way it is.*

---

## Table of Contents

1. [The Big Picture — What This System Does](#1-the-big-picture)
2. [How Data Flows End-to-End](#2-how-data-flows-end-to-end)
3. [Every File Explained](#3-every-file-explained)
4. [Key Concepts You Should Understand](#4-key-concepts-you-should-understand)
5. [How the Technologies Connect](#5-how-the-technologies-connect)
6. [Interview Talking Points Per Component](#6-interview-talking-points-per-component)
7. [Deployment Guide](#7-deployment-guide)

---

## 1. The Big Picture

### What problem does this solve?

Companies have internal documents (reports, manuals, policies) that employees need to query. The problems with existing approaches:
- **Keyword search** (like Ctrl+F) misses meaning — searching "revenue" doesn't find "income"
- **Plain LLMs** (like ChatGPT) don't know your private data and make things up
- **Simple RAG** retrieves once and generates — if the first retrieval misses the mark, the answer is still wrong

This system solves all three:
1. **Hybrid semantic + keyword search** — finds by meaning AND exact match
2. **Private data grounded** — LLM only uses what's in your documents
3. **Agentic loop** — if the first search isn't good enough, it searches again with a smarter query

### What makes it "agentic"?

A regular chatbot is a function: `input → output`. Done.

An agent is a loop: `input → action → observe result → decide next action → ...`. The agent can check its own work and course-correct.

In this project, the "agent" is the LangGraph state machine. After retrieving chunks, it asks itself: "Is this enough to answer the question?" If not, it generates a better search query and retrieves again. This is called **self-RAG** (the system critiques itself).

---

## 2. How Data Flows End-to-End

### Flow 1: Uploading a PDF

```
You drop a PDF on the frontend
  │
  ▼
Frontend sends: POST /api/v1/collections/{id}/documents (with the file)
  │
  ▼
backend/api/documents.py receives it:
  - Saves file to disk (uploads/ folder)
  - Creates a Document record in PostgreSQL with status="processing"
  - Returns immediately: {document_id, status: "processing"}
  - Schedules the ingestion as a background task
  │
  ▼ (runs in background, doesn't block the response)
backend/services/ingestion_service.py:
  Step 1: pypdf extracts text from each page → [{page: 1, text: "..."}, ...]
  Step 2: ALL pages merged into one continuous text block (cross-page chunking)
  Step 3: split_into_chunks() splits by paragraphs with page tracking
  Step 4: embedding_service.embed_batch() converts each chunk to a 384-dim vector
  Step 5: qdrant_service.upsert_chunks() stores vectors + metadata in Qdrant
  Step 6: db.update(document.status = "done", chunk_count = N)
  │
  ▼
Frontend polls GET /api/v1/documents/{id}/status every 2 seconds
  └── Shows "✓ 42 chunks" when done
```

### Flow 2: Asking a Question (the Agentic Loop)

```
You type a question → frontend sends POST /api/v1/chat/stream
  │
  ▼
backend/api/chat.py:
  - Creates/finds conversation session in PostgreSQL (commit(), not flush())
  - Saves user message to PostgreSQL (commit() ensures background tasks can see it)
  - Creates Langfuse trace (for observability)
  - Calls: agent_graph.ainvoke(initial_state)
  - Returns StreamingResponse (SSE stream)
  │
  ▼
backend/agent/graph.py (LangGraph state machine):
  
  START
    │
    ▼
  [retrieval_node] — backend/agent/nodes.py
    1. Takes current_query from state (first time = user's question)
    2. Calls embedding_service.embed_text(query) → 384-dim vector
    3. Calls qdrant_service.hybrid_search() → top 10 similar chunks (no score_threshold)
    4. Appends chunks to state["retrieved_chunks"]
    5. Emits SSE event: {type: "retrieval", iteration: 1}
    6. Increments state["retrieval_count"]
    │
    ▼
  [sufficiency_node] — backend/agent/nodes.py
    1. Builds a prompt: "Given this question and these chunks, is the context sufficient?"
    2. Calls llm_client.generate() → gets JSON response
    3. Parses JSON: {sufficient: true/false, reason: "...", refined_query: "..."}
    4. Prompt leans towards sufficient=true — only says false if chunks are entirely irrelevant
    5. Updates state["is_sufficient"] and state["refined_query"]
    │
    ├── sufficient=True OR retrieval_count >= 2 → [generation_node]
    │
    └── sufficient=False AND retries remaining → loop back to [retrieval_node]
                                                  (uses refined_query next time)
    │
    ▼
  [generation_node] — backend/agent/nodes.py
    1. Deduplicates chunks (same source+index shouldn't appear twice)
    2. Builds a grounded prompt: "Answer ONLY using: [chunks]"
    3. Streams tokens via llm_client.stream() → each token becomes SSE event
    4. Emits {type: "token", content: "The answer is..."} for each token
    5. Builds source citations → emits {type: "sources", data: [...]}
    6. Logs full call to Langfuse
    │
    ▼
  END (agent finishes)
    │
    ▼
Back in backend/api/chat.py:
  - Saves assistant message + sources to PostgreSQL
  - Spawns async task: RAGAS evaluation
  - RAGAS runs evaluate_response() → scores
  - Saves RAGAS scores to PostgreSQL and Langfuse
  - Emits: {type: "done", session_id: "..."}
  │
  ▼
Frontend receives each SSE event as it arrives:
  - "retrieval" → shows "🔍 Retrieved 1×" badge (updates to "context retrieved" once answer starts)
  - "token" → appends to chat bubble in real-time
  - "sources" → renders clickable source chips
  - "done" → enables the input box again
```

### Flow 3: Deleting a Document

```
User clicks 🗑 on a document → DELETE /api/v1/documents/{document_id}
  │
  ▼
backend/api/documents.py:
  - Loads the document from PostgreSQL (needs filename + collection_id for Qdrant)
  - qdrant_service.delete_document_chunks(collection_id, filename)
      → Qdrant filter-delete: removes all points where payload.source == filename
  - Deletes uploaded file from disk (best-effort)
  - Deletes PostgreSQL row
  - Returns 204 No Content
  │
  ▼
Frontend removes the document from state.documents and re-renders the list
```

### Flow 4: Deleting a Collection

```
User clicks 🗑 next to the collection dropdown → DELETE /api/v1/collections/{collection_id}
  │
  ▼
backend/api/collections.py:
  - Loads the collection from PostgreSQL
  - qdrant_service.delete_collection(collection_id)
      → Drops the entire Qdrant collection (all vectors for this collection)
  - db.delete(collection) + db.commit()
      → SQLAlchemy cascade="all, delete" automatically deletes:
        documents, conversation_sessions, messages
  - Returns 204 No Content
  │
  ▼
Frontend clears all state, resets UI to "No collection selected"
```

---

## 3. Every File Explained

### Root Level

**`pyproject.toml`**
The project manifest. Lists all dependencies with version constraints.
`uv sync` reads this and installs everything. Think of it like `package.json` for Python.

**`.env.example`**
Template for the `.env` file that holds your secret API keys.
The real `.env` is never committed to Git — `.gitignore` blocks it.
`pydantic-settings` in `backend/config.py` reads the `.env` automatically.

**`docker-compose.yml`**
Defines 4 services: FastAPI app, PostgreSQL, Qdrant, Langfuse.
`docker compose up` starts all of them together, creates a network between them
so they can talk to each other using their service names (e.g., `postgres:5432`).

**`Dockerfile`**
Instructions for building the FastAPI app as a Docker image.
Railway uses this for deployment.

---

### `backend/config.py`

This is the **single source of truth** for all configuration.

`pydantic-settings` reads every field from environment variables (or the `.env` file).
If a required variable is missing, the app crashes at startup with a clear error.

`@lru_cache` makes `get_settings()` run only once — the `Settings` object is
created on first call and then returned from cache on every subsequent call.
This means the whole app shares one configuration instance.

**How it connects:** every other module does `from backend.config import get_settings`
and calls `get_settings()` to get database URLs, API keys, etc.

---

### `backend/models/database.py`

This file does two things:

**1. Database connection:**
`create_async_engine()` opens a pool of connections to PostgreSQL.
"Async" means database queries don't block — while waiting for PostgreSQL,
FastAPI can handle other requests.

`async_session_factory` creates session objects. A "session" is like a transaction
scope — changes are batched and committed together.

**2. Table definitions:**
Each class (Collection, Document, ConversationSession, Message) maps to a
PostgreSQL table. `create_tables()` creates them on startup if they don't exist.

The `relationship()` fields with `cascade="all, delete"` mean: when you delete a
Collection, SQLAlchemy automatically deletes all its Documents, Sessions, and Messages.

**How it connects:** `get_db_session()` is a FastAPI dependency — route handlers
declare `db: AsyncSession = Depends(get_db_session)` and FastAPI injects the session.

---

### `backend/models/schemas.py`

Pydantic models define the shape of API requests and responses.

When a request comes in, FastAPI uses the Pydantic model to validate it automatically.
If `collection_id` is not a valid UUID, FastAPI returns a 422 error before your code runs.

When a route returns a Pydantic model, FastAPI serializes it to JSON automatically.

The `model_config = {"from_attributes": True}` tells Pydantic it can create a
schema object from a SQLAlchemy model directly (converting the ORM object to JSON).

---

### `backend/services/llm_client.py`

The LLM client hides the complexity of two different LLM providers behind one interface.

**Why two providers?**
- Gemini 2.0 Flash is free but has rate limits
- If Gemini is down or rate-limited, `_use_groq_fallback = True` and all subsequent calls use Groq

**Two modes:**
- `generate()` — returns the complete response as a string. Used for structured tasks
  (sufficiency check) where we need the full JSON before continuing.
- `stream()` — returns an async generator that yields tokens one by one. Used for
  the chat answer so the user sees words appearing in real-time.

**`@retry` decorator:** from the `tenacity` library. If `generate()` raises an exception,
it waits 1-4 seconds and retries (up to 2 attempts) before giving up.

**`run_in_executor`:** The Gemini SDK is synchronous (blocking). Running it directly
in async code would freeze the event loop. `run_in_executor` runs it in a thread pool,
so the async loop stays responsive while Gemini is processing.

---

### `backend/services/embedding_service.py`

Converts text to vectors using `sentence-transformers`.

**The model (`all-MiniLM-L6-v2`):**
- Downloads ~90MB the first time (cached in `~/.cache`)
- Runs entirely on CPU — no GPU needed
- Produces 384-dimensional vectors
- "MiniLM" = mini language model, "L6" = 6 layers, "v2" = version 2

**`embed_text` vs `embed_batch`:**
- `embed_text`: one string → one vector. Used for query embedding.
- `embed_batch`: list of strings → list of vectors. Used for ingestion.
  Batch processing is much faster because the model processes multiple texts
  in parallel internally (matrix operations are efficient in batches).

---

### `backend/services/qdrant_service.py`

All Qdrant operations in one place.

**What Qdrant stores:**
Each document chunk is stored as:
1. An ID (UUID string)
2. A vector (384 floats) — used for similarity search
3. A payload (dict) — metadata: source filename, page, chunk text, etc.

**`hybrid_search`:**
Sends the query vector to Qdrant, which returns the N most similar vectors using
cosine similarity. We deliberately avoid setting a `score_threshold` — the
`all-MiniLM-L6-v2` model's cosine scores are often 0.15–0.40 for genuinely relevant
chunks, so a threshold like 0.3 would silently drop good results. Instead, we let the
sufficiency node and the LLM judge relevance. Default `top_k=10` (increased from 5
for better recall).

**`delete_document_chunks`:**
Uses Qdrant's filter-based delete to remove all points whose `source` payload field
matches a given filename. This is how a single document is cleanly removed without
touching other documents in the same collection.

**`delete_collection`:**
Drops the entire Qdrant collection (all vectors for that collection ID).

**`_collection_name`:**
We prefix collection names with `rag_` to avoid collisions if someone uses the
same Qdrant instance for other projects. "Collection" in Qdrant ≈ "table" in SQL.

---

### `backend/services/ingestion_service.py`

The most complex service — the full pipeline from raw PDF to searchable chunks.

**`extract_text_from_pdf`:**
`pypdf.PdfReader` opens the binary PDF and extracts the text layer page by page.
Important: scanned PDFs (photos of pages) have no text layer — they return empty strings.
Those would need OCR (optical character recognition), which is out of scope for this project.

**Cross-page chunking (important improvement):**
Instead of splitting each page independently (which breaks sentences that span page
boundaries), we first merge ALL page texts into one continuous document. A
`page_char_offsets` list tracks which character positions belong to which page, so
each chunk still knows its approximate page number even after merging.

**Why this matters:** if a paragraph starts on page 3 and ends on page 4, the old
per-page approach would split that paragraph into two incomplete halves. Cross-page
merging keeps it whole.

**`split_into_chunks`:**
Why not just split every 400 characters? Because a sentence might look like:
```
...The algorithm uses three phases: data ingestion,
[SPLIT HERE]
model training, and inference.
```
The split makes "ingestion, model training, and inference" appear in the next chunk
without context. The reader (LLM) can't tell that "ingestion" was the start of a list.

Paragraph-aware splitting splits at `\n\n` (paragraph breaks) first, then only
falls back to character limits. This preserves complete thoughts.

**Overlap:** The last 200 characters of the previous chunk are included at the
start of the next chunk. This ensures that context spanning a chunk boundary
is still available in both chunks.

---

### `backend/services/langfuse_client.py`

Wraps the Langfuse SDK for observability.

**Trace → Spans hierarchy:**
- One `trace` per user request (the whole question → answer cycle)
- One `span` per LLM call within that trace (retrieval, sufficiency, generation)

The `trace_id` is returned in the final SSE `done` event so you can show the
Langfuse trace in an interview by clicking a link.

**Graceful degradation:** If Langfuse keys are missing, `_enabled = False`
and all methods become no-ops. The app still works — you just don't get traces.

---

### `mcp_server/server.py`

The MCP tool server. This runs as a separate process.

**Why separate?**
MCP tools are designed to be reusable across different agent frameworks.
The same tools can be used by Claude Desktop, LangGraph, your custom agent, etc.

**`@mcp.tool()` decorator:**
Registers a function as an MCP tool. FastMCP reads the function's type annotations
and docstring to expose them in the MCP manifest (so agents know what each tool does).

**`@mcp.resource()` decorator:**
Resources are different from tools — they're read-only data that agents can
subscribe to. Tools perform actions, resources provide context.

**Input validation:**
The `_validate_query` and `_validate_uuid` helpers run on every tool call.
Empty strings, over-length inputs, and invalid UUIDs are rejected before any
real work happens. This prevents crashes and potential prompt injection attacks.

---

### `backend/agent/state.py`

`AgentState` is a `TypedDict` — a Python type that says "this dict must have these exact keys with these types."

This is **only a type hint**, not a real class. It exists so:
1. Your IDE can autocomplete `state["retrieved_chunks"]` correctly
2. `mypy` can catch bugs like accessing `state["retreived_chunks"]` (typo)

The state is like a clipboard that gets passed between nodes. Each node can read
any field and return a partial update (only the keys it changed).

---

### `backend/agent/nodes.py`

The three "worker functions" in the agent loop.

**Why return partial updates?**
LangGraph merges each node's returned dict into the full state.
This means nodes don't need to know about fields they don't touch.
`retrieval_node` returns `{retrieved_chunks, retrieval_count, sse_events}` —
it doesn't need to include `answer` or `sources` (those it didn't change).

**`sse_events` list:**
Nodes append events to this list. The API route drains the list to send SSE events
to the browser. This is a simple way to "communicate out" from nodes without
needing a separate message queue.

**`SufficiencyResult` (Pydantic model):**
The LLM returns a JSON string. We parse it into `SufficiencyResult` using
`model_validate_json()`. If the JSON is malformed, Pydantic raises `ValidationError`.
We catch that and default to `sufficient=True` (fail open — better to generate
a possibly imperfect answer than to crash).

**Sufficiency prompt is tuned to be lenient:** it only returns `sufficient=false`
if the chunks are *entirely* unrelated. If there's any partial overlap, it says
sufficient. This avoids unnecessary re-retrieval on good-enough context.

**`MAX_RETRIEVAL_ATTEMPTS = 2`:** Max 2 retrieval rounds before forcing generation.
This keeps latency reasonable — the second retrieval already has the refined query.

---

### `backend/agent/graph.py`

The LangGraph "wiring" — connects nodes with edges.

**Conditional edges:**
`add_conditional_edges(source, routing_fn, mapping)`:
- After `sufficiency` node runs, call `_should_continue_retrieval(state)`
- The function returns a string key
- LangGraph looks up that key in the mapping to find the next node

This is how "if/else" logic works in a LangGraph graph — not with Python if/else
inside a node, but with routing functions on edges.

**`graph.compile()`:**
Validates the graph structure (no dead ends, no unreachable nodes) and optimizes it.
Returns a compiled graph object that can be called with `.ainvoke()`.

The compiled graph is created once at module import time (`agent_graph = build_agent_graph()`)
and reused for every request. It's stateless — the state is passed in each invocation.

---

### `backend/api/collections.py`

Routes for managing collections:
- `POST /api/v1/collections` — create collection
- `GET /api/v1/collections` — list all
- `GET /api/v1/collections/{id}` — get one
- `GET /api/v1/collections/{id}/documents` — list documents in a collection
- **`DELETE /api/v1/collections/{id}`** — delete collection + all its data (Qdrant + Postgres cascade)

---

### `backend/api/documents.py`

Routes for managing documents:
- `POST /api/v1/collections/{id}/documents` — upload PDF (background ingestion)
- `GET /api/v1/documents/{id}/status` — poll processing status
- **`DELETE /api/v1/documents/{id}`** — delete a document and all its Qdrant chunks

**Why `commit()` not `flush()` for upload:**
The background task opens a NEW database session. It can only see rows that have been
committed to the database. If we only `flush()` (which writes within the current
transaction without committing), the background task can't find the document row,
so ingestion silently never runs. Using `commit()` ensures the background task can
see the document.

---

### `backend/api/chat.py`

The most complex route because it coordinates everything.

**`StreamingResponse`:**
Instead of returning JSON at the end of the request, this returns a generator that
yields text continuously. The browser's `EventSource` API consumes this stream.

**`asyncio.create_task()`:**
Used to run RAGAS evaluation and score saving truly in the background — after the
stream has ended and the user has their answer. The user doesn't wait for RAGAS.

**`_format_sse(data)`:**
SSE has a specific format: `data: {json}\n\n`. The double newline is required —
it signals the end of one event to the browser.

---

### `backend/eval/evaluator.py`

RAGAS takes a `Dataset` object with `question`, `answer`, `contexts` (and optionally `ground_truth`).
It runs each metric by calling the LLM judge (Gemini) to evaluate quality.

**The 4 metrics in plain English:**

1. **Faithfulness** — The evaluator LLM checks each claim in the answer against the context.
   "Does this statement appear in or logically follow from the retrieved chunks?"
   Score = fraction of claims that are supported. Catches hallucination.

2. **Answer Relevancy** — The evaluator asks: "Does this answer address the question?"
   Measured by generating alternative questions from the answer and seeing how similar
   they are to the original question. Catches off-topic or evasive answers.

3. **Context Recall** — Requires a ground_truth answer. Checks whether the retrieved chunks
   contain all the information needed to construct the ground_truth.
   Score = fraction of ground_truth sentences covered by retrieved chunks.

4. **Context Precision** — Of the retrieved chunks, how many were actually used in the answer?
   Catches over-retrieval (retrieving irrelevant chunks along with relevant ones).

---

### `frontend/index.html`

Single-file frontend — HTML, CSS, and JS in one file.

**Two-panel layout:**
- Left panel: collection management (create/delete), PDF upload, document list (with delete)
- Right panel: chat interface with streaming messages, source chips, RAGAS badges

**Collection isolation:**
Switching collections clears `state.documents`, `state.current_session_id`, and the chat area.
Documents are fetched fresh from the backend API each time. This prevents cross-collection
chat bleed (a bug where the previous collection's chat stayed visible).

**Delete UX:**
- 🗑 next to collection dropdown → deletes entire collection with confirmation
- 🗑 appears on document row hover → deletes that document with confirmation
- Both make a `DELETE` API call, then update local state and re-render

**SSE indicator update:**
The retrieval indicator shows "🔍 Retrieved 1× — searching for better context…" during
retrieval, then automatically updates to "🔍 Retrieved 1× — context retrieved" once
the first answer token arrives.

---

## 4. Key Concepts You Should Understand

### What is an async function?

In Python, `async def` creates a coroutine — a function that can be "paused" while
waiting (e.g., for a database query or LLM response) and resumed later.

`await` pauses the current coroutine and lets other coroutines run.

Without async: request 1 asks the DB → everything freezes for 50ms → request 2 waits.
With async: request 1 asks the DB → pauses → request 2 runs → DB responds → request 1 resumes.

This is how FastAPI handles thousands of concurrent requests without threads.

### What is a Python generator?

A generator is a function that `yield`s values one at a time instead of returning all at once.

```python
def gen():
    yield 1
    yield 2
    yield 3

for x in gen():
    print(x)  # prints 1, 2, 3
```

An `AsyncGenerator` is the async version — it yields values but can also `await`.
We use it in `llm_client.stream()` to yield tokens one by one as the LLM produces them.

### What is a TypedDict?

A `TypedDict` is just a type hint. It tells tools (IDE, mypy) what keys a dict should have.
It doesn't enforce anything at runtime — if you put the wrong type in, Python won't crash.
But mypy WILL catch it at type-check time.

```python
class MyDict(TypedDict):
    name: str
    age: int

d: MyDict = {"name": "Alice", "age": 25}  # correct
d: MyDict = {"name": "Alice"}  # mypy error: missing 'age'
```

### What is Pydantic?

Pydantic validates data at runtime. When you do `model.model_validate_json(string)`,
Pydantic parses the JSON and checks every field's type. If something is wrong, it
raises `ValidationError` with a clear message.

This is why FastAPI uses Pydantic for request/response models — you get automatic
validation and clear error messages without writing any validation code.

### What is a LangGraph "node"?

A node is just a Python async function with signature:
```python
async def my_node(state: AgentState) -> dict:
    # do work
    return {"key": "updated_value"}
```

The returned dict is a PARTIAL update — LangGraph merges it with the current state.

---

## 5. How the Technologies Connect

```
User request
    │
    ├─ FastAPI (request routing, validation, dependency injection)
    │   └─ Pydantic (validates request body, serializes responses)
    │
    ├─ SQLAlchemy async (saves/reads PostgreSQL data)
    │   └─ PostgreSQL (stores collections, documents, messages, eval scores)
    │
    ├─ LangGraph (state machine, orchestrates the agent loop)
    │   ├─ sentence-transformers (local embedding model)
    │   ├─ Qdrant (vector similarity search + delete by filter)
    │   ├─ google-generativeai / groq (LLM calls)
    │   └─ FastMCP (MCP protocol, connects to mcp_server/server.py)
    │
    ├─ Langfuse (records every LLM call with timing and tokens)
    │
    └─ RAGAS (evaluates answer quality asynchronously)
```

---

## 6. Interview Talking Points Per Component

### On FastAPI:
> "I chose FastAPI over Flask because it's async-native — every route can handle
> other requests while waiting for database or LLM responses. It also auto-generates
> OpenAPI docs at /docs, which I can show live in an interview."

### On LangGraph:
> "LangGraph models the agent as a state machine — nodes are processing steps,
> edges define transitions. The sufficiency check creates a conditional edge that
> either loops back to retrieval or proceeds to generation. This is much cleaner
> than managing the retry loop manually, and LangGraph handles async execution,
> state persistence, and error recovery."

### On MCP:
> "The agent doesn't call Qdrant directly. It uses MCP — the Model Context Protocol.
> My MCP server exposes three tools: document search, document metadata, and web search.
> The agent calls them through the standard MCP protocol. This means the same tools
> can be used from any MCP-compatible environment — Claude Desktop, Cursor, or another
> agent framework — without any changes."

### On RAGAS:
> "After every answer, the system grades itself using RAGAS with Gemini as the judge.
> I measure faithfulness (are claims grounded in context?), relevancy (does it address
> the question?), context recall (did we retrieve the right chunks?), and context precision
> (were all retrieved chunks actually used?). The scores are stored in PostgreSQL and
> sent directly to the Langfuse trace dashboard."

### On Qdrant:
> "I chose Qdrant over Pinecone for three reasons: native hybrid search (vector + BM25
> keyword combined), a free cloud tier with no credit card required, and the ability
> to run locally in Docker during development. At this scale, these advantages clearly
> outweigh Pinecone's managed ops benefits."

### On the agentic loop:
> "Standard RAG retrieves once and generates. My system checks sufficiency.
> After the first retrieval, Gemini evaluates whether the retrieved context contains
> enough information to answer the question. If not, it generates a refined query and
> retrieves again — up to 2 times. I removed a strict score_threshold that was silently
> filtering out relevant chunks, and tuned the sufficiency prompt to avoid unnecessary
> re-retrieval."

### On delete operations:
> "The delete document endpoint does two things atomically: it removes the Qdrant vectors
> for that document by filtering on the 'source' payload field, and deletes the Postgres
> row. SQLAlchemy's cascade='all, delete' handles collection deletion — deleting one
> collection row automatically deletes all its documents, sessions, and messages."

### On chunking:
> "I rewrote the chunking pipeline to merge all page texts into one continuous document
> before splitting. This prevents sentences that span page boundaries from being cut
> in half. Page numbers are still tracked via character offset ranges, so each chunk
> knows which page it came from."

---

## 7. Deployment Guide

### Local Development

```bash
# 1. Copy environment template
cp .env.example .env
# Edit .env with your API keys

# 2. Start all services
docker compose up

# 3. Visit
# App: http://localhost:8000
# API docs: http://localhost:8000/docs
# Langfuse: http://localhost:3000
```

### Railway Deployment (Production)

1. **Qdrant Cloud setup:**
   - Go to https://cloud.qdrant.io → create free cluster
   - Copy cluster URL and API key to Railway env vars

2. **Railway setup:**
   - Connect GitHub repo to Railway
   - Add environment variables (GEMINI_API_KEY, GROQ_API_KEY, etc.)
   - Railway reads the Dockerfile and builds automatically
   - PostgreSQL: add Railway PostgreSQL plugin (copies DATABASE_URL automatically)

3. **GitHub Actions:**
   - Add `RAILWAY_TOKEN` to GitHub repo secrets
   - CI runs on every push: pytest → mypy → deploy to Railway on main

4. **After deployment:**
   - Update README with live Railway URL
   - Run RAGAS baseline on the live deployment to populate scores
   - Record 6-minute demo video for the README
