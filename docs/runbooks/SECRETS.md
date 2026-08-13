# Secrets Inventory & Rotation

This is the authoritative list of every live credential this stack depends on: where it lives, what it's for, and how to rotate it if it's ever exposed (accidental commit, leaked screenshot, laptop loss, etc.).

**Source of truth:** a shared Bitwarden vault (free tier is enough for this team size). The `.env`/`gcp_sa.json` files on the server and any developer's laptop are *working copies*, not the source of truth - if a working copy and the vault ever disagree, the vault wins and working copies get overwritten from it, not the other way around.

Neither `infra/.env` nor `secrets/gcp_sa.json` are committed to git (see `.gitignore`) - this file documents them without ever containing real values.

---

## Inventory

| Secret | Where it lives | Used by | Rotate from |
|---|---|---|---|
| `POSTGRES_PASSWORD` | `infra/.env` | `dadaai-postgres`, `dadaai-n8n` | Self-chosen - just generate a new one and update both places (see below) |
| `ANTHROPIC_API_KEY` | `infra/.env`, `workflowiq/.env.example` | WorkflowIQ (Claude calls), SOPBot n8n (Claude Extraction node) | [console.anthropic.com](https://console.anthropic.com) → API Keys |
| `AIRTABLE_API_TOKEN` | `infra/.env` | WorkflowIQ, SOPBot n8n (Airtable nodes) | Airtable → account → Developer Hub → Personal access tokens |
| `AIRTABLE_BASE_ID` | `infra/.env` | Same as above | Not a secret in the traditional sense (visible in any Airtable URL for the base), but treat as sensitive since it identifies which base to target |
| `STREAMLIT_APP_PASSWORD` | `infra/.env` | WorkflowIQ operator login (`app/auth.py`) | Self-chosen - pick a new one, update `.env`, redeploy |
| `GHL_API_KEY` | `infra/.env` | SOPBot n8n (email notifications via GHL, see `docs/adr/001-email-via-ghl.md`) | GoHighLevel → Settings → API Keys |
| `GHL_LOCATION_ID` | `infra/.env` | Same as above | Not secret by itself, but scopes which GHL sub-account the key acts on |
| `VAPI_WEBHOOK_SECRET` | `infra/.env` | Validates that inbound webhook calls to n8n's `/sopbot-call-ended` endpoint really came from Vapi | Vapi dashboard → the phone number's webhook config |
| `N8N_ENCRYPTION_KEY` | `infra/.env` | Encrypts every credential n8n itself stores internally | **Cannot be rotated in place** - see warning below |
| `secrets/gcp_sa.json` (whole file) | `secrets/` directory | WorkflowIQ (`google_drive/reader.py`), potential future backup scripts | GCP Console → IAM & Admin → Service Accounts → `sopbot-service-account@sopbot-501317.iam.gserviceaccount.com` → Keys → Add key (then delete the old one) |

---

## `N8N_ENCRYPTION_KEY` - special case, read this first

This key encrypts every credential (Anthropic key, Airtable token, GHL key, Vapi secret) *inside n8n's own database*. It is generated once at first setup and is **not meant to be rotated** - per n8n's own design, changing it makes every previously-stored credential unreadable, and every integration has to be re-entered from scratch inside the n8n UI.

- If it's ever exposed: treat it as a full incident, not a simple rotation. Anyone with this key **and** a copy of the n8n database backup could decrypt every credential ever stored. In that scenario, rotate every *other* secret in this table (they're the ones actually exposed), then optionally regenerate `N8N_ENCRYPTION_KEY` as a clean break, accepting the one-time cost of re-entering all n8n credentials.
- Store it in Bitwarden **today** if it isn't there already - this is the one secret in this table that is genuinely unrecoverable if lost (confirmed in `docs/runbooks/dr_recovery.md`).

---

## Rotating a normal secret (general procedure)

1. Generate the new value at the provider (see "Rotate from" column above).
2. Update the value in Bitwarden first (source of truth).
3. Update `/root/dadaai/infra/.env` on the server:
   ```bash
   ssh root@167.233.94.171
   nano /root/dadaai/infra/.env   # update the one line
   ```
4. Restart whichever container reads that variable:
   ```bash
   cd /root/dadaai/infra
   docker compose up -d dadaai-workflowiq   # or dadaai-n8n, as applicable
   ```
5. For n8n specifically: credentials used by workflow nodes (Anthropic, Airtable, GHL) are stored *inside n8n's credential store*, not read from `infra/.env` at runtime - you also need to update them in the n8n UI (Credentials → the relevant credential → update value) for the running workflow to actually pick up the new value. `infra/.env`'s copy is only used if you rebuild the n8n credential from scratch.
6. Update your local working copy of `infra/.env` (and anyone else's) so it doesn't silently drift from what's live.
7. Confirm nothing broke: run a real test call through SOPBot and a real analysis through WorkflowIQ (per the verification habits already established for this project - see project notes on prior incidents where "looks fine" wasn't actually fine).

---

## What's NOT covered here

- Vapi account login itself (not an API key used by the running system, just dashboard access) - manage via your normal account security (strong password + 2FA), not this doc.
- Hetzner console access - same as above.
- GitHub repo access - manage via GitHub's own collaborator/branch-protection settings, not this doc.
