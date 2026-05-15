# Documentation Topics Guide

This directory contains the ultimate study guide and documentation hub for the Agentic RAG system.

Here is a recommended reading order and exactly what each document explains:

### 1. `architecture.md` (The Blueprint) - **Read First**
* **What it explains:** Provides a high-level visual and textual representation of the system. It contains Mermaid diagrams showing the frontend, backend, LangGraph agent, MCP server, and databases. It also includes a table of "Technology Choices and Trade-offs" (e.g., why Gemini over GPT-4o, why Qdrant over Pinecone).
* **Purpose:** Perfect for quickly grasping the system architecture or explaining the tech stack to someone else (like an interviewer).

### 2. `project_explainer.md` (The Master Guide) - **Read Second**
* **What it explains:** This is the deepest dive into the project. It breaks down the big picture, explains the exact data flows (what happens when you upload a PDF or send a message), and literally explains **every single file** in your codebase. It also covers key concepts, how the technologies connect, and provides a deployment guide.
* **Purpose:** To help you understand the *why* and *how* of the entire codebase line-by-line and component-by-component.

### 3. `llm-theory.md` (Interview Prep) - **Read Third**
* **What it explains:** Answers 5 core theoretical questions: What is RAG? Semantic vs. Keyword search? What causes hallucinations? What are embeddings? What is MCP?
* **Purpose:** This bridges the gap between your code and the underlying AI concepts, giving you solid, articulate answers for technical discussions or interviews.

### 4. `chunking-comparison.md` (Technical Decision Justification)
* **What it explains:** Compares fixed-size chunking vs. paragraph-aware chunking, explaining why you chose paragraph-aware chunking and how it improves the system by preserving semantic boundaries.
* **Purpose:** Proves that your design decisions were intentional and backed by reasoning, which is a senior-level engineering trait.

### 5. `eval-results.md` (Metrics & Tracking)
* **What it explains:** A template for tracking your RAGAS evaluation metrics (Faithfulness, Answer Relevancy, Context Recall, Context Precision). It compares baseline scores against different configurations (like chunking strategies or single vs. multi-hop retrieval).
* **Purpose:** Shifts the project from "it seems to work" to "it works and here is the quantitative proof."

---

### Is this enough to understand the entire project (including the code)?
**Absolutely, YES.** 
If you read the `project_explainer.md` alongside `architecture.md`, you will have a complete mental model of how the code works, how the LangGraph agent routes data, and how the API connects to the frontend. It leaves practically no stone unturned. The other three documents provide the theoretical backing and quantitative metrics to prove *why* the code was written that way.
