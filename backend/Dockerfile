FROM python:3.14-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 && rm -rf /var/lib/apt/lists/*

# Pinned rather than :latest so Dependabot tracks it — a floating tag drifts
# silently on every rebuild and no bump ever shows up for review.
COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv

# Install third-party deps first (cached layer)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source and install the package
COPY src/ ./src/
COPY alembic.ini ./
COPY alembic/ ./alembic/
RUN uv sync --frozen --no-dev

ENV PYTHONUNBUFFERED=1

# Release version stamped by the GHCR workflow (git tag); "dev" for local builds.
# Read by the opt-in update check to compare against GitHub releases.
ARG APP_VERSION=dev
ENV APP_VERSION=$APP_VERSION

CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn igab.main:app --host 0.0.0.0 --port 8000"]
