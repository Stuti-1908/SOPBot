#!/bin/bash
# Nightly n8n SQLite backup — WAL-safe via SQLite's online backup (VACUUM INTO).
#
# Why not `docker cp` the live DB (the previous approach)?
#   n8n runs SQLite in WAL mode. Copying database.sqlite while n8n is writing
#   yields a TORN snapshot: the -wal/-shm files are not captured atomically with
#   the main file, so the copy can fail integrity_check even though the live DB
#   is perfectly sound. That produced a false "possible corruption" alert on
#   2026-07-29. VACUUM INTO asks SQLite itself for a consistent point-in-time
#   snapshot, which is safe to take against a live, actively-written database.
set -euo pipefail

BACKUP_DIR=/root/n8n_backups
CONTAINER=n8n-n8n-1
DB_IN_CONTAINER=/home/node/.n8n/database.sqlite
SNAP_IN_CONTAINER=/home/node/.n8n/_backup_snapshot.sqlite
NODE_PATH_SQLITE=/usr/local/lib/node_modules/n8n/node_modules/.pnpm/sqlite3@5.1.7/node_modules
KEEP_DAYS=7
STAMP=$(date -u +%Y%m%d_%H%M%S)
TMP=$(mktemp -d)
OUT="$BACKUP_DIR/n8n_${STAMP}.sqlite"

mkdir -p "$BACKUP_DIR"
log(){ echo "[$(date -u '+%F %T')] $*"; }

cleanup(){
  rm -rf "$TMP"
  # always clear the in-container snapshot, even on failure
  docker exec "$CONTAINER" rm -f "$SNAP_IN_CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# 0) make sure a stale snapshot from a previous crashed run does not block VACUUM INTO
docker exec "$CONTAINER" rm -f "$SNAP_IN_CONTAINER" >/dev/null 2>&1 || true

# 1) ask SQLite for a consistent snapshot of the live DB (WAL-safe)
log "creating consistent snapshot via VACUUM INTO ..."
docker exec -e NODE_PATH="$NODE_PATH_SQLITE" "$CONTAINER" node -e '
const s = require("sqlite3");
const db = new s.Database(process.argv[1], s.OPEN_READONLY, (e) => {
  if (e) { console.error("OPEN ERR", e.message); process.exit(1); }
});
db.run("VACUUM INTO ?", [process.argv[2]], (e) => {
  if (e) { console.error("VACUUM ERR", e.message); process.exit(1); }
  db.close();
});
' "$DB_IN_CONTAINER" "$SNAP_IN_CONTAINER"

# 2) pull the snapshot out (safe: nothing is writing to it)
docker cp "$CONTAINER:$SNAP_IN_CONTAINER" "$TMP/db.sqlite"

# 3) integrity gate — a VACUUM INTO snapshot should always pass; if it does not,
#    the LIVE database really is damaged and this alert is genuine.
RESULT=$(sqlite3 "$TMP/db.sqlite" "PRAGMA integrity_check;" 2>&1 | head -1)
if [ "$RESULT" != "ok" ]; then
  log "INTEGRITY FAILED ($RESULT) — NOT saving this backup (live DB may be corrupt!)"
  echo "$STAMP integrity_check=$RESULT" >> "$BACKUP_DIR/CORRUPTION_DETECTED.log"
  exit 2
fi

# 4) save + compress
cp "$TMP/db.sqlite" "$OUT"
gzip -f "$OUT"
log "backup OK -> ${OUT}.gz ($(du -h "${OUT}.gz" | cut -f1))"

# 5) rotate: delete backups older than KEEP_DAYS
find "$BACKUP_DIR" -name 'n8n_*.sqlite.gz' -mtime +"$KEEP_DAYS" -delete
log "rotation done; $(ls "$BACKUP_DIR"/n8n_*.sqlite.gz 2>/dev/null | wc -l) backups retained"
