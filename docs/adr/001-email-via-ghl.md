# ADR 001: Use GoHighLevel (GHL) for Transactional Email

**Date:** 2026-06-29  
**Status:** Accepted  
**Deciders:** Stuti, Dwayne

## Context
SOPBot needs to send two types of email notifications:
1. Owner alert (Dwayne + Stuti) when a new SOP is generated
2. Ops alert when an error occurs

We needed to decide between: GHL (already have credentials), SendGrid, AWS SES, or SMTP.

## Decision
Use GoHighLevel API for all outgoing email from n8n.

## Rationale
- Credentials already exist (no new vendor onboarding)
- GHL is already used for client communications at DadaAI
- Centralises email sending in one platform for tracking/auditing
- n8n has a native HTTP Request node — no special integration needed

## Consequences
- GHL API rate limits apply (check GHL docs for sending limits)
- If GHL account is suspended, email notifications stop — acceptable risk for v1
- Future: evaluate dedicated transactional email provider (SendGrid/SES) if volume grows

## Implementation
n8n HTTP Request node → `POST https://services.leadconnectorhq.com/conversations/messages`  
Auth: Bearer `{{GHL_API_KEY}}`  
Location ID: `{{GHL_LOCATION_ID}}`
