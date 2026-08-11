import asyncio
import logging
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from backend.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

EMBEDDING_DIM = 768
EMBEDDING_MODEL_NAME = "models/text-embedding-004"

class EmbeddingService:
    def __init__(self):
        self._embeddings = GoogleGenerativeAIEmbeddings(
            model=EMBEDDING_MODEL_NAME,
            google_api_key=settings.gemini_api_key
        )

    async def embed_text(self, text: str) -> list[float]:
        return await self._embeddings.aembed_query(text)

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self._embeddings.aembed_documents(texts)

embedding_service = EmbeddingService()
