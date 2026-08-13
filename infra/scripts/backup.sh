#!/usr/bin/env bash
# Nightly Postgres backup — run via cron as deploy user.
# Add to crontab: 0 2 * * * /opt/dadaai/infra/scripts/backup.sh >> /var/log/dadaai-backup.log 2>&1
set -euo pipefail

BACKUP_DIR="/opt/dadaai/backups/postgres"
CONTAINER="postgres"
POSTGRES_DB="${POSTGRES_DB:-n8n}"
POSTGRES_USER="${POSTGRES_USER:-n8n_user}"
RETENTION_DAYS=7
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
FILENAME="$BACKUP_DIR/${POSTGRES_DB}_${TIMESTAMP}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup of $POSTGRES_DB..."
docker exec "$CONTAINER" pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "$FILENAME"
echo "[$(date)] Backup written to $FILENAME ($(du -sh "$FILENAME" | cut -f1))"

echo "[$(date)] Pruning backups older than $RETENTION_DAYS days..."
find "$BACKUP_DIR" -name "*.sql.gz" -mtime "+$RETENTION_DAYS" -delete

echo "[$(date)] Backup complete."
