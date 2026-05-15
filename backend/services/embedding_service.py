
import asyncio
import logging
from functools import lru_cache

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


EMBEDDING_DIM = 384
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _load_model() -> SentenceTransformer:
    logger.info(f"Loading embedding model: {EMBEDDING_MODEL_NAME}")
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    logger.info("Embedding model loaded successfully")
    return model


class EmbeddingService:

    def __init__(self):
        self._model: SentenceTransformer | None = None

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = _load_model()
        return self._model

    async def embed_text(self, text: str) -> list[float]:
        loop = asyncio.get_event_loop()
        model = self._get_model()
        vector = await loop.run_in_executor(None, lambda: model.encode(text).tolist())
        return vector

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        loop = asyncio.get_event_loop()
        model = self._get_model()
        vectors = await loop.run_in_executor(
            None,
            lambda: model.encode(texts, batch_size=32, show_progress_bar=False).tolist(),
        )
        return vectors


embedding_service = EmbeddingService()
