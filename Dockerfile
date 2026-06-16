FROM python:3.13-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.11.15 /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies first (cached layer — only invalidated when lock file changes)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application source
COPY main.py database.py scraper.py scheduler.py ./
COPY templates/ templates/

# Persistent storage for the SQLite database
RUN mkdir -p /data && \
    useradd -r -u 1001 -s /bin/false appuser && \
    chown appuser /data

USER appuser

ENV DATABASE_URL=sqlite:////data/ovoprice.db

EXPOSE 8000

VOLUME ["/data"]

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
