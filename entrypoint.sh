#!/bin/sh
set -e

# Install the muse package if the dev volume mount is present.
# This lets the server-side release analysis service import muse.plugins.code.
if [ -f /muse/pyproject.toml ]; then
    echo "Muse volume detected — installing muse in editable mode..."
    pip install -e /muse --quiet --root-user-action=ignore 2>/dev/null || true
fi

echo "Running database migrations..."
alembic upgrade head

echo "Starting MuseHub..."
exec uvicorn musehub.main:app \
    --host 0.0.0.0 \
    --port 10003 \
    --workers 4 \
    --proxy-headers \
    --forwarded-allow-ips='*'
