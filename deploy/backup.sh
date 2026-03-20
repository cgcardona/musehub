#!/usr/bin/env bash
# Postgres daily backup script — run via cron on the EC2 instance.
# Dumps the musehub database and rotates backups older than 14 days.
#
# Install (on EC2):
#   sudo mkdir -p /opt/backups/musehub
#   sudo chown ubuntu:ubuntu /opt/backups/musehub
#   chmod +x /opt/musehub/deploy/backup.sh
#   crontab -e
#   # Add this line (runs daily at 3 AM):
#   0 3 * * * /opt/musehub/deploy/backup.sh >> /var/log/musehub-backup.log 2>&1

set -euo pipefail

APP_DIR="/opt/musehub"
BACKUP_DIR="/opt/backups/musehub"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/musehub_${TIMESTAMP}.sql.gz"
RETAIN_DAYS=14

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."

# Load DB_PASSWORD from the app's .env
DB_PASSWORD=$(grep '^DB_PASSWORD=' "$APP_DIR/.env" | cut -d'=' -f2-)

sudo docker compose -f "$APP_DIR/docker-compose.yml" exec -T postgres \
    env PGPASSWORD="$DB_PASSWORD" \
    pg_dump -U musehub musehub \
    | gzip > "$BACKUP_FILE"

echo "[$(date)] Backup written: $BACKUP_FILE ($(du -sh "$BACKUP_FILE" | cut -f1))"

echo "[$(date)] Removing backups older than $RETAIN_DAYS days..."
find "$BACKUP_DIR" -name "musehub_*.sql.gz" -mtime "+$RETAIN_DAYS" -delete

echo "[$(date)] Backup complete. Files kept:"
ls -lh "$BACKUP_DIR"
