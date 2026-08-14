# Runbook: Disaster Recovery — Rebuild SOPBot + WorkflowIQ

**When to use:** The current Hetzner VPS (167.233.94.171) is unrecoverable (hardware failure, accidental deletion, account loss).
**RTO target:** < 4 hours
**RPO target:** < 24 hours (nightly n8n SQLite backup) for workflow definitions and execution history. Airtable and Google Drive data is not covered by this backup - see "What is NOT covered" below.

---

## Important: this stack is co-hosted, not standalone

`dadaai-n8n`, `dadaai-workflowiq`, and `dadaai-postgres` (see `infra/docker-compose.yml`) do **not** run their own reverse proxy and do **not** own ports 80/443. They join an existing Docker network (`n8n_default`) and rely on a Caddy container from a separate, pre-existing setup at `/root/n8n/` on the same box (which also hosts an unrelated n8n instance, `n8n-n8n-1`, running dozens of workflows for other projects such as Relentless AI).

This means rebuilding "just the DadaAI stack" on a fresh VPS is **not** a drop-in `docker compose up`. You must either:
- (a) rebuild the entire shared box, including the other project's `/root/n8n/` setup and Caddyfile, or
- (b) stand up DadaAI's own Caddy + network from scratch on the new box (a real, if small, architecture change from what's running today).

Confirm which situation you're in before starting. This runbook assumes (b): a clean rebuild of just the DadaAI stack with its own routing.

---

## Prerequisites
- Access to: the private GitHub repo (`https://github.com/Stuti-1908/SOPBot`), Airtable, Vapi dashboard, GCP console, GHL
- The current `infra/.env` file (holds `N8N_ENCRYPTION_KEY`, Postgres credentials, Anthropic/Airtable/GHL API keys, `STREAMLIT_APP_PASSWORD`). This file is intentionally **not** in git (see `.gitignore`) - it must be recovered from wherever it's stored outside the repo (password manager / secure backup). **`N8N_ENCRYPTION_KEY` cannot be regenerated** - without the original value, all encrypted credentials stored inside n8n's workflows become unreadable and every integration credential must be re-entered from scratch.
- `secrets/gcp_sa.json` (Google service account key for Drive access) - also gitignored, recover from secure storage.
- Latest n8n backup file (`.sqlite.gz`) - see "Restoring the backup" below for where these actually live.

---

## What IS covered by nightly backup

Two separate n8n instances run on this box (see "this stack is co-hosted" above), each with its own backup job:

- `/root/n8n_backup.sh` (03:00 daily) backs up **`n8n-n8n-1`** - a different, unrelated n8n instance on this shared server (Relentless AI and other projects, not SOPBot). WAL-safe SQLite snapshot via `VACUUM INTO`, saved to `/root/n8n_backups/n8n_<timestamp>.sqlite.gz`, retained 7 days.
- `/root/dadaai_backup.sh` (03:05 daily) backs up **`dadaai-n8n`** - SOPBot's actual n8n instance, which runs on Postgres (`dadaai-postgres`), not SQLite. Produces a `pg_dump` at `/root/dadaai_backups/dadaai_postgres_<timestamp>.sql.gz`, retained 7 days.

**Until 2026-08-14, `dadaai-n8n`'s own database was never backed up at all** - only the exported workflow JSON in `sopbot/n8n-workflows/` existed outside the live container (which itself was only added 2026-08-13). The two scripts were easy to conflate since they look similar and run minutes apart; confirm which one you actually need when restoring (check the `CONTAINER=` line at the top of each script if unsure).

**Offsite:** `/root/dadaai_backup.sh` also uploads its own output and the latest `n8n-n8n-1` SQLite backup to a Backblaze B2 bucket (`sopbot-backups-dadaai`, credentials in `infra/.env` as `B2_*`) via `rclone`, so both backups now survive a total loss of this server, not just database corruption. `n8n_backup.sh` itself does not upload anything - the offsite step piggybacks on the second script running after it.

## What is NOT covered by any automated backup

- **Airtable** (Clients, Calls Log, WorkflowIQ Runs tables) - hosted entirely by Airtable, not backed up by anything in this stack. Airtable has its own revision history/snapshot features on paid plans - check your plan's retention window separately.
- **Google Drive content** (client SOP docs, generated reports) - hosted by Google, not backed up by anything in this stack. Google Drive's own trash/version history is the only safety net unless configured otherwise.
- **The n8n workflow *source* (JSON)** is now mitigated: `sopbot/n8n-workflows/sopbot_main.json` and `sopbot_error_handler.json` are committed to git as of 2026-08-13, so the workflow logic itself survives even a total loss of the server and its backups. The nightly SQLite backup additionally captures execution history and any workflow edits made since the last git export - re-export and commit periodically, or after any workflow change.

---

## Steps

### 1. Provision new Hetzner VPS
- Create a CX-tier (or equivalent) Ubuntu 22.04/24.04 instance
- Add your SSH public key during provisioning
- Note the new IP

### 2. Install Docker + Docker Compose
```bash
ssh root@<new-ip>
curl -fsSL https://get.docker.com | sh
```
(`infra/scripts/harden.sh` covers basic OS hardening - review it before running, it has not been re-verified against a fresh Ubuntu image recently.)

### 3. Clone the repo and recover secrets
```bash
git clone https://github.com/Stuti-1908/SOPBot.git /root/dadaai
mkdir -p /root/dadaai/secrets
# Restore infra/.env and secrets/gcp_sa.json from your secure backup location
# (these are gitignored and will NOT come from the clone)
chmod 600 /root/dadaai/infra/.env /root/dadaai/secrets/gcp_sa.json
```

### 4. Stand up networking
Since this is a fresh box (no pre-existing shared Caddy), either:
- Add a minimal Caddy service to `infra/docker-compose.yml` pointing at `dadaai-n8n:5678` and `dadaai-workflowiq:8501`, or
- Point your own reverse proxy / load balancer at the container ports once they're up.

Update DNS A records for whatever domains you're using to the new IP (propagation: 5-60 min).

### 5. Start the stack
```bash
cd /root/dadaai/infra
docker compose up -d
# Wait for dadaai-postgres and dadaai-n8n to report healthy:
docker ps
```

### 6. Restore dadaai-n8n's database (Postgres)
Download the latest `dadaai_postgres_<timestamp>.sql.gz` from the B2 bucket (`sopbot-backups-dadaai`) or wherever else it was retrieved from, then:
```bash
gunzip -k dadaai_postgres_<timestamp>.sql.gz
docker exec -i dadaai-postgres psql -U dadaai_user -d dadaai_n8n < dadaai_postgres_<timestamp>.sql
docker restart dadaai-n8n
```
If no backup file survived (full server + backup loss), skip to step 7 and rebuild from the exported JSON instead - you will lose execution history but not workflow logic.

(The `n8n_<timestamp>.sqlite.gz` backups relate to a *different* n8n instance on the original server - not needed to restore SOPBot. See "What IS covered" above.)

### 7. Re-import workflows (always do this even after restoring a DB backup, to confirm workflows are present and active)
- n8n UI → Import → `sopbot/n8n-workflows/sopbot_main.json`
- n8n UI → Import → `sopbot/n8n-workflows/sopbot_error_handler.json`
- Re-enter credentials for each node (Anthropic API key, GHL API key, Airtable token, Vapi webhook secret) - **credential values are never exported**, only references
- Activate both workflows

### 8. Verify end-to-end
- Call the Vapi test number → confirm a Google Doc SOP is generated and Airtable Calls Log gets a new row
- Open WorkflowIQ at the new URL → log in → run a test analysis with a real or sample SOP → confirm a PDF downloads
- Check Airtable `Clients`/`Calls Log` and the WorkflowIQ runs table for the new test records

### 9. Re-enable nightly backup cron
```bash
cp /root/dadaai/infra/scripts/n8n_backup.sh /root/n8n_backup.sh
chmod +x /root/n8n_backup.sh
crontab -e
# Add:
0 3 * * * /root/n8n_backup.sh >> /root/n8n_health.log 2>&1
```
(`n8n_backup.sh` is committed at `infra/scripts/n8n_backup.sh` as of 2026-08-13 - previously it existed only on the server.)

---

## Known gaps in this runbook (as of 2026-08-14)

- `infra/scripts/harden.sh` has not been re-verified against a current Ubuntu image.
- This runbook has not been dry-run on an actual fresh VPS - treat as best-effort until tested.
- The B2 offsite upload has only been verified as a manual one-off run and via the real cron entry existing - not yet confirmed to succeed unattended over multiple nights. Check `/root/dadaai_backups/backup.log` after a few days to confirm.
