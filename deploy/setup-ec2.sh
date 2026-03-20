#!/usr/bin/env bash
# Run this ON the EC2 instance (via SSH) after provisioning.
# Installs Docker, nginx, Certbot, deploys MuseHub, and obtains SSL.
#
# Usage (from your Mac, after DNS has propagated):
#   scp -i ~/.ssh/musehub-key.pem -r deploy/ ubuntu@musehub.ai:/home/ubuntu/
#   ssh -i ~/.ssh/musehub-key.pem ubuntu@musehub.ai
#   chmod +x ~/deploy/setup-ec2.sh && ~/deploy/setup-ec2.sh

set -euo pipefail

DOMAIN="musehub.ai"
APP_DIR="/opt/musehub"
REPO_URL="https://github.com/cgcardona/musehub.git"   # update to your actual repo URL

echo "==> [1/8] System update"
sudo apt-get update -qq && sudo apt-get upgrade -y -qq

echo "==> [2/8] Install Docker"
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
echo "    Docker installed. NOTE: You may need to log out/in for group to take effect."
echo "    For this script we use 'sudo docker' throughout."

echo "==> [3/8] Install nginx + Certbot"
sudo apt-get install -y -qq nginx python3-certbot-nginx

echo "==> [4/8] Configure nginx (HTTP only for now — Certbot will add SSL)"
sudo tee /etc/nginx/sites-available/musehub > /dev/null << 'NGINX_CONF'
server {
    listen 80;
    listen [::]:80;
    server_name musehub.ai www.musehub.ai;

    client_max_body_size 50m;

    location / {
        proxy_pass         http://127.0.0.1:10003;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
    }
}
NGINX_CONF

sudo ln -sf /etc/nginx/sites-available/musehub /etc/nginx/sites-enabled/musehub
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
echo "    nginx configured"

echo "==> [5/8] Clone MuseHub repo"
sudo git clone "$REPO_URL" "$APP_DIR"
sudo chown -R ubuntu:ubuntu "$APP_DIR"
echo "    Cloned to $APP_DIR"

echo "==> [6/8] Create production .env"
if [ ! -f "$APP_DIR/.env" ]; then
    ACCESS_TOKEN_SECRET=$(openssl rand -hex 32)
    DB_PASSWORD=$(openssl rand -hex 16)
    WEBHOOK_SECRET_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || echo "GENERATE_ME_WITH_FERNET")

    cat > "$APP_DIR/.env" << EOF
DEBUG=false
DATABASE_URL=postgresql+asyncpg://musehub:${DB_PASSWORD}@postgres:5432/musehub
DB_PASSWORD=${DB_PASSWORD}
ACCESS_TOKEN_SECRET=${ACCESS_TOKEN_SECRET}
CORS_ORIGINS=["https://musehub.ai", "https://www.musehub.ai"]
WEBHOOK_SECRET_KEY=${WEBHOOK_SECRET_KEY}
MUSEHUB_ALLOWED_ORIGINS=["musehub.ai", "www.musehub.ai"]
EOF
    echo "    .env created with generated secrets"
    echo ""
    echo "    !! SAVE THESE — they are in $APP_DIR/.env !!"
    cat "$APP_DIR/.env"
    echo ""
else
    echo "    .env already exists, skipping generation"
fi

echo "==> [7/8] Start MuseHub with Docker Compose"
cd "$APP_DIR"
sudo docker compose -f docker-compose.yml up -d --build
echo "    Waiting 15 seconds for containers to start..."
sleep 15
sudo docker compose -f docker-compose.yml ps
echo "    MuseHub started"

echo "==> [8/8] Obtain Let's Encrypt SSL certificate"
echo "    (DNS must be propagated to $DOMAIN for this to succeed)"
sudo certbot --nginx \
    -d "$DOMAIN" -d "www.$DOMAIN" \
    --non-interactive \
    --agree-tos \
    --redirect \
    --email "hello@musehub.ai"

echo ""
echo "============================================================"
echo "  SETUP COMPLETE"
echo "============================================================"
echo "  https://$DOMAIN is live"
echo "  App dir   : $APP_DIR"
echo "  Secrets   : $APP_DIR/.env  (back these up!)"
echo ""
echo "  Next: run deploy/seed.sh to create your account + repos"
echo "============================================================"
