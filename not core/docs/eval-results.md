# RAGAS Evaluation Results

## Baseline Scores

| Metric | Score | Target | Status |
|---|---|---|---|
| Faithfulness | — | > 0.80 | Pending |
| Answer Relevancy | — | > 0.75 | Pending |
| Context Recall | — | > 0.70 | Pending |
| Context Precision | — | > 0.70 | Pending |

*Run `uv run python -m scripts.run_ragas_baseline` to populate scores.*

---

## Before / After: Chunking Strategy Change

| Metric | Fixed-size | Paragraph | Delta |
|---|---|---|---|
| Faithfulness | — | — | — |
| Answer Relevancy | — | — | — |
| Context Recall | — | — | — |
| Context Precision | — | — | — |

---

## Before / After: Agentic Re-retrieval

Testing 10 "hard" questions that require multi-hop reasoning.

| Metric | Single retrieval | With re-retrieval (up to 3×) | Delta |
|---|---|---|---|
| Faithfulness | — | — | — |
| Answer Relevancy | — | — | — |

---

## Interview Talking Point

> "Every answer the system generates is automatically graded by RAGAS using Gemini as the judge. The scores are stored in PostgreSQL and pushed directly to the Langfuse trace. I ran baselines on 25 hand-crafted questions covering single-hop, multi-hop, and should-refuse cases. I can show you the live dashboard and pull up any specific trace in Langfuse."
