# MuseHub — Production Dockerfile
# Multi-stage build: builder installs deps into wheels; runtime copies only the wheels.
#
# Layer invalidation guide (when to rebuild):
#   requirements.txt changed  →  docker compose build musehub
#   Python code changed       →  no rebuild (override.yml bind-mounts musehub/ tests/ etc.)

FROM python:3.14-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt


FROM python:3.14-slim AS runtime

WORKDIR /app

RUN groupadd -r musehub && useradd -r -g musehub musehub

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache-dir /wheels/*

COPY --chown=musehub:musehub musehub/ ./musehub/
COPY --chown=musehub:musehub alembic/ ./alembic/
COPY --chown=musehub:musehub tourdeforce/ ./tourdeforce/
COPY --chown=musehub:musehub alembic.ini pyproject.toml ./

COPY --chown=musehub:musehub entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

RUN mkdir -p /data && chown -R musehub:musehub /data && chmod 755 /data

USER musehub

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 10003

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:10003/api/v1/openapi.json')" || exit 1

ENTRYPOINT ["./entrypoint.sh"]
