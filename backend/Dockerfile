FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install third-party deps first (cached layer)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source and install the package
COPY src/ ./src/
COPY alembic.ini ./
COPY alembic/ ./alembic/
RUN uv sync --frozen --no-dev

ENV PYTHONUNBUFFERED=1

CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn igab.main:app --host 0.0.0.0 --port 8000"]
