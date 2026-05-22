FROM python:3.11-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml ./

RUN uv sync --no-dev

COPY backend/ ./backend/
COPY mcp_server/ ./mcp_server/
COPY frontend/ ./frontend/

RUN mkdir -p uploads

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
