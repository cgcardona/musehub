# MuseHub — Production Dockerfile
# Multi-stage build: builder installs deps into wheels; runtime copies only the wheels.
#
# Layer invalidation guide (when to rebuild):
#   requirements.txt changed  →  docker compose build musehub
#   Python code changed       →  no rebuild (override.yml bind-mounts musehub/ tests/ etc.)

FROM python:3.11-slim as builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt


FROM python:3.11-slim as runtime

WORKDIR /app

RUN groupadd -r musehub && useradd -r -g musehub musehub

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache-dir /wheels/*
RUN pip install --no-cache-dir pytest-cov

COPY --chown=musehub:musehub musehub/ ./musehub/
COPY --chown=musehub:musehub tests/ ./tests/
COPY --chown=musehub:musehub scripts/ ./scripts/
COPY --chown=musehub:musehub alembic/ ./alembic/
COPY --chown=musehub:musehub tourdeforce/ ./tourdeforce/
COPY --chown=musehub:musehub alembic.ini pyproject.toml ./

RUN mkdir -p /data && chown -R musehub:musehub /data && chmod 755 /data

USER musehub

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 10003

CMD ["uvicorn", "musehub.main:app", "--host", "0.0.0.0", "--port", "10003"]
