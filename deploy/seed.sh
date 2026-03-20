#!/usr/bin/env bash
# Run ON the EC2 instance after the app is live.
# Creates your admin account, mints a JWT, seeds code repos + MIDI repos.
#
# Usage:
#   ssh -i ~/.ssh/musehub-key.pem ubuntu@musehub.ai
#   chmod +x /opt/musehub/deploy/seed.sh && /opt/musehub/deploy/seed.sh

set -euo pipefail

APP_DIR="/opt/musehub"
CONTAINER="musehub-musehub-1"   # adjust if docker compose names it differently

echo "==> Checking container name..."
CONTAINER=$(sudo docker compose -f "$APP_DIR/docker-compose.yml" ps --format json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d[0]['Name'])" 2>/dev/null || echo "musehub-musehub-1")
echo "    Container: $CONTAINER"

echo "==> Running seed_production.py (gabriel's account + 5 code repos + 5 MIDI repos)..."
sudo docker compose -f "$APP_DIR/docker-compose.yml" exec musehub \
    python3 /app/scripts/seed_production.py

echo "==> Minting admin JWT for gabriel..."
sudo docker compose -f "$APP_DIR/docker-compose.yml" exec musehub python3 - << 'PYEOF'
import hashlib, uuid
from musehub.auth.tokens import generate_access_code

# Same stable ID used by seed_production.py
GABRIEL_ID = str(uuid.UUID(bytes=hashlib.md5("prod-gabriel-cgcardona".encode()).digest()))
token = generate_access_code(user_id=GABRIEL_ID, duration_days=365, is_admin=True)

print("\n" + "="*60)
print("ADMIN JWT FOR gabriel (valid 365 days):")
print("="*60)
print(token)
print("="*60)
print("\nAdd to your Muse CLI config:")
print(f"  muse config set hub.token {token}")
print(f"  muse config set hub.url https://musehub.ai")
print("="*60 + "\n")
PYEOF

echo ""
echo "============================================================"
echo "  SEED COMPLETE"
echo "============================================================"
echo "  Copy the JWT above and configure your Muse CLI:"
echo "    muse config set hub.token <token>"
echo "    muse config set hub.url https://musehub.ai"
echo ""
echo "  Then you can push repos:"
echo "    cd ~/path/to/muse && muse push"
echo "============================================================"
