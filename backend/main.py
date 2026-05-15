import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from backend.api.chat import router as chat_router
from backend.api.collections import router as collections_router
from backend.api.documents import router as documents_router
from backend.api.eval import router as eval_router
from backend.config import get_settings
from backend.models.database import create_tables
from backend.models.schemas import HealthResponse
from backend.services.qdrant_service import qdrant_service

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    """
    logger.info("Starting Agentic RAG System...")

    await create_tables()
    logger.info("Database tables ready")

    qdrant_ok = await qdrant_service.ping()
    if qdrant_ok:
        logger.info("Qdrant connection: OK")
    else:
        logger.warning("Qdrant not reachable — search will fail until it connects")

    logger.info(f"App running at http://{settings.app_host}:{settings.app_port}")

    yield

    logger.info("Shutting down...")


app = FastAPI(
    title="Agentic RAG System",
    description="LangGraph agent + MCP tools + RAGAS evaluation for PDF Q&A",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(collections_router)
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(eval_router)


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    return HealthResponse(status="ok", version="1.0.0")

app.mount("/static", StaticFiles(directory="frontend"), name="static")

@app.get("/", include_in_schema=False)
async def serve_frontend():
    frontend_path = Path("frontend/index.html")
    if frontend_path.exists():
        return FileResponse(frontend_path)
    return {"message": "Agentic RAG API is running. Visit /docs for API documentation."}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=(settings.app_env == "development"),
        log_level=settings.log_level.lower(),
    )