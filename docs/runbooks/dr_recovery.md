# Runbook: Disaster Recovery — Rebuild n8n + WorkflowIQ on New Hetzner VPS

**When to use:** Current VPS is unrecoverable (hardware failure, accidental deletion).  
**RTO target:** < 4 hours  
**RPO target:** < 24 hours (nightly Postgres backup)

---

## Prerequisites
- Access to: GitHub repo, Airtable, Vapi dashboard, GCP console, GHL
- Latest Postgres backup (from `/opt/dadaai/backups/postgres/` or wherever you stored offsite copies)
- The `N8N_ENCRYPTION_KEY` (stored in your password manager — **CRITICAL, cannot be recovered**)

---

## Steps

### 1. Provision new Hetzner VPS
- Create CX21 (or equivalent) Ubuntu 22.04 instance
- Add your SSH public key during provisioning
- Note the new IP

### 2. Point DNS to new IP
- In your DNS provider: update A record for `n8n.dadaai.com` and `wiq.dadaai.com` to new IP
- TTL propagation: 5–60 minutes

### 3. Harden the server
```bash
ssh root@<new-ip>
bash <(curl -fsSL https://raw.githubusercontent.com/your-org/dadaai/main/infra/scripts/harden.sh)
```
Then SSH back as `deploy` user.

### 4. Clone repo and configure secrets
```bash
git clone https://github.com/your-org/dadaai.git /opt/dadaai
cp /opt/dadaai/infra/.env.example /opt/dadaai/infra/.env
# Fill in ALL values — especially N8N_ENCRYPTION_KEY (must match original)
nano /opt/dadaai/infra/.env
```

### 5. Restore Postgres backup
```bash
cd /opt/dadaai/infra
docker compose up -d postgres
# Wait for healthy
docker exec -i postgres psql -U n8n_user -d n8n < /path/to/backup.sql
```

### 6. Start all services
```bash
docker compose up -d
```

### 7. Restore n8n workflows
- n8n UI → Import each JSON from `sopbot/n8n-workflows/`
- Re-enter credentials (Anthropic API key, GHL API key, Airtable token)
- Activate both workflows

### 8. Verify
- Call the Vapi test number → confirm SOP is generated
- Open WorkflowIQ at `wiq.dadaai.com` → run a test analysis
- Check Airtable Calls Log and WorkflowIQ Runs for new records

### 9. Set up nightly backup cron on new server
```bash
crontab -e
# Add:
0 2 * * * /opt/dadaai/infra/scripts/backup.sh >> /var/log/dadaai-backup.log 2>&1
```
