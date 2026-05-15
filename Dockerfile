# Dockerfile — builds the FastAPI app container
# Used by Railway for deployment and by docker-compose for local dev

# Use Python 3.11 slim image (smaller = faster to pull)
FROM python:3.11-slim

# Set working directory inside the container
WORKDIR /app

# Install uv for fast dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files first (Docker caches this layer if unchanged)
COPY pyproject.toml ./

# Install all dependencies
RUN uv sync --no-dev

# Copy the rest of the application code
COPY backend/ ./backend/
COPY mcp_server/ ./mcp_server/
COPY frontend/ ./frontend/

# Create the uploads directory
RUN mkdir -p uploads

# Expose the port FastAPI runs on
EXPOSE 8000

# Start the app
CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
