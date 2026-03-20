#!/bin/sh
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Starting MuseHub..."
exec uvicorn musehub.main:app \
    --host 0.0.0.0 \
    --port 10003 \
    --proxy-headers \
    --forwarded-allow-ips='*'
