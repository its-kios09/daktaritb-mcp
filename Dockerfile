# DaktariTB MCP — production container image
# Built for Render.com (but works anywhere Docker runs).
#
# Render assigns the listening port via $PORT env var. We must bind to 0.0.0.0
# (not 127.0.0.1) or the platform cannot route traffic to the container.

FROM python:3.11-slim-bookworm

# Prevent Python from writing .pyc files and buffering stdout/stderr —
# makes container logs show up immediately in Render's log viewer.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system deps needed for building some Python wheels.
# curl kept for Render's optional health check tooling.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy project metadata first so `pip install` caches when code changes
# but deps don't.
COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

RUN pip install --upgrade pip && pip install .

# Run as a non-root user (defense in depth).
RUN useradd --create-home --shell /bin/bash daktari
USER daktari

# Render injects $PORT. Default to 8000 for local `docker run`.
ENV PORT=8000
EXPOSE 8000

# Use sh -c so $PORT is expanded at container start (not build).
CMD ["sh", "-c", "uvicorn daktaritb_mcp.server:app --host 0.0.0.0 --port ${PORT}"]
