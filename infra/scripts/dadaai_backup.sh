#!/bin/bash
# Nightly backup of dadaai-n8n's actual database (Postgres), plus offsite
# upload of both this and the pre-existing n8n-n8n-1 SQLite backup.
#
# Why this script exists separately from n8n_backup.sh:
#   n8n_backup.sh backs up n8n-n8n-1 (a different, unrelated n8n instance
#   on this shared box - see infra/docker-compose.yml comments). SOPBot's
#   own n8n (dadaai-n8n) uses DB_TYPE=postgresdb against dadaai-postgres,
#   not SQLite, so it was never covered by any backup until this script -
#   only the workflow JSON export in sopbot/n8n-workflows/ existed outside
#   the live container. Discovered 2026-08-14.
set -euo pipefail

BACKUP_DIR=/root/dadaai_backups
CONTAINER=dadaai-postgres
DB_USER=dadaai_user
DB_NAME=dadaai_n8n
KEEP_DAYS=7
STAMP=$(date -u +%Y%m%d_%H%M%S)
OUT="$BACKUP_DIR/dadaai_postgres_${STAMP}.sql"

mkdir -p "$BACKUP_DIR"
log(){ echo "[$(date -u '+%F %T')] $*"; }

# 1) pg_dump is safe to run against a live, actively-written database -
#    it runs inside a single transaction and produces a consistent snapshot
#    without needing to stop writes, unlike a raw file copy would.
log "dumping $DB_NAME from $CONTAINER ..."
docker exec -e PGPASSWORD="$(docker exec "$CONTAINER" printenv POSTGRES_PASSWORD)" "$CONTAINER" \
  pg_dump -U "$DB_USER" -d "$DB_NAME" --no-owner --no-privileges > "$OUT"

# 2) sanity check: a valid dump should at least contain a PostgreSQL header
#    within its first few lines (pg_dump emits a leading blank line before
#    the "-- PostgreSQL database dump" comment, so check a small window,
#    not just line 1).
if ! head -5 "$OUT" | grep -q "PostgreSQL database dump"; then
  log "DUMP LOOKS INVALID - not keeping this backup"
  rm -f "$OUT"
  exit 2
fi

gzip -f "$OUT"
log "backup OK -> ${OUT}.gz ($(du -h "${OUT}.gz" | cut -f1))"

# 3) rotate: delete backups older than KEEP_DAYS
find "$BACKUP_DIR" -name 'dadaai_postgres_*.sql.gz' -mtime +"$KEEP_DAYS" -delete
log "rotation done; $(ls "$BACKUP_DIR"/dadaai_postgres_*.sql.gz 2>/dev/null | wc -l) backups retained"

# 4) offsite upload to Backblaze B2 - both this backup and the latest
#    n8n-n8n-1 SQLite backup (produced separately by n8n_backup.sh, which
#    runs just before this script in cron).
if [ -f /root/dadaai/infra/.env ]; then
  set -a; source /root/dadaai/infra/.env; set +a
fi

if [ -n "${B2_BUCKET:-}" ] && command -v rclone >/dev/null 2>&1; then
  log "uploading to offsite backup (B2 bucket: $B2_BUCKET) ..."
  rclone copy "${OUT}.gz" "b2backup:${B2_BUCKET}/" --s3-no-check-bucket -q \
    && log "  dadaai postgres backup uploaded" \
    || log "  WARNING: offsite upload of postgres backup failed"

  LATEST_N8N_SQLITE=$(ls -t /root/n8n_backups/n8n_*.sqlite.gz 2>/dev/null | head -1)
  if [ -n "$LATEST_N8N_SQLITE" ]; then
    rclone copy "$LATEST_N8N_SQLITE" "b2backup:${B2_BUCKET}/" --s3-no-check-bucket -q \
      && log "  n8n-n8n-1 sqlite backup uploaded" \
      || log "  WARNING: offsite upload of sqlite backup failed"
  fi
else
  log "B2_BUCKET not set or rclone missing - skipping offsite upload"
fi
