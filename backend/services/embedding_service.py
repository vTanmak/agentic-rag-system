import asyncio
import logging
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

EMBEDDING_DIM = 3072
EMBEDDING_MODEL_NAME = "models/gemini-embedding-001"

class EmbeddingService:
    def __init__(self):
        self._embeddings = None

    def _get_embeddings(self):
        if self._embeddings is None:
            self._embeddings = GoogleGenerativeAIEmbeddings(
                model=EMBEDDING_MODEL_NAME,
                google_api_key=settings.gemini_api_key
            )
        return self._embeddings

    async def embed_text(self, text: str) -> list[float]:
        return await self._get_embeddings().aembed_query(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self._get_embeddings().aembed_documents(texts)

embedding_service = EmbeddingService()
