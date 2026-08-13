# ADR 002: Self-Host n8n on Hetzner via Docker

**Date:** 2026-06-29  
**Status:** Accepted  
**Deciders:** Stuti, Dwayne

## Context
n8n is required as the webhook orchestration layer for SOPBot.
Options: n8n Cloud (managed SaaS) vs self-hosted on VPS.

## Decision
Self-host n8n on a Hetzner VPS (CX21 or equivalent) using Docker Compose with Postgres backing store.

## Rationale
- Cost: Hetzner CX21 ~€5/month vs n8n Cloud ~$50/month at this usage level
- Control: Full access to workflow JSON for git versioning
- Data residency: Transcripts (Confidential/PII) stay on our infrastructure
- Flexibility: Can co-host WorkflowIQ on same VPS cost-effectively

## Consequences
- We own uptime responsibility — mitigated with Uptime Kuma monitoring
- Must manage server hardening, TLS (Caddy), and backups
- N8N_ENCRYPTION_KEY must be backed up securely — loss = unrecoverable credentials
- Upgrade path: pull new n8n image, `docker compose up -d` — test on staging first

## Implementation
See `infra/docker-compose.yml` — Caddy + n8n + Postgres stack.
