import asyncio
import logging
import uuid
import warnings
from typing import Optional
from backend.config import get_settings
from backend.models.schemas import RAGASScores

warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)
settings = get_settings()

async def evaluate_response(
    question: str,
    answer: str,
    contexts: list[str],
    ground_truth: Optional[str] = None,
) -> RAGASScores:

    import sys
    from unittest.mock import MagicMock
    if "langchain_community.chat_models.vertexai" not in sys.modules:
        sys.modules["langchain_community.chat_models.vertexai"] = MagicMock()

    try:
        from ragas import evaluate
        from ragas.metrics import (
            faithfulness,
            answer_relevancy,
            context_recall,
            context_precision,
        )
        answer_relevancy.strictness = 1
        from datasets import Dataset
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        from langchain_groq import ChatGroq

        data = {
            "question": [question],
            "user_input": [question],
            "answer": [answer],
            "response": [answer],
            "contexts": [contexts],
            "retrieved_contexts": [contexts],
        }

        metrics_to_run = [faithfulness, answer_relevancy]
        if ground_truth:
            data["ground_truth"] = [ground_truth]
            data["reference"] = [ground_truth]
            metrics_to_run.append(context_precision)
            metrics_to_run.append(context_recall)

        dataset = Dataset.from_dict(data)

        judge_llm = ChatGroq(
            model=settings.groq_model,
            api_key=settings.groq_api_key,
            temperature=0,
        )
        judge_embeddings = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=settings.gemini_api_key,
        )

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: evaluate(
                dataset,
                metrics=metrics_to_run,
                llm=judge_llm,
                embeddings=judge_embeddings,
                raise_exceptions=False,
            ),
        )

        scores_dict = result.to_pandas().iloc[0].to_dict()

        return RAGASScores(
            faithfulness=_safe_float(scores_dict.get("faithfulness")),
            answer_relevancy=_safe_float(scores_dict.get("answer_relevancy")),
            context_recall=_safe_float(scores_dict.get("context_recall")),
            context_precision=_safe_float(scores_dict.get("context_precision")),
        )

    except Exception as e:
        logger.error(f"RAGAS evaluation failed: {e}")
        return RAGASScores()

async def save_eval_scores(
    session,
    message_id: uuid.UUID,
    scores: RAGASScores,
) -> None:

    from backend.models.database import Message
    
    try:
        message = await session.get(Message, message_id)
        if message:
            message.eval_scores_json = scores.model_dump(exclude_none=True)
            await session.commit()
            logger.info(f"RAGAS scores saved for message {message_id}")
    except Exception as e:
        logger.error(f"Failed to save RAGAS scores: {e}")

def _safe_float(value) -> Optional[float]:
    import math
    try:
        if value is None:
            return None
        f_val = float(value)
        if math.isnan(f_val):
            return None
        return f_val
    except (TypeError, ValueError):
        return None