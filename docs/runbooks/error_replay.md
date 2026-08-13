# Runbook: Replaying a Failed SOPBot Call

**When to use:** A call completed but Status = Error in Calls Log, and the SOP was not created.

---

## Steps

### 1. Find the failed record
- Airtable → **Calls Log** → filter Status = Error
- Note the **Call ID** and **Error Detail**

### 2. Diagnose the error
Common causes:

| Error Detail contains | Likely cause | Fix |
|-----------------------|--------------|-----|
| `JSON parse error` | Claude returned malformed JSON | Check prompt in `sopbot/prompts/transcript_extraction.txt` |
| `Drive API error` | Service account lacks folder access | Re-share Drive folder with SA email |
| `Airtable` | API token expired or rate limited | Rotate token in Airtable → Account → API |
| `Company not matched` | Employee said unknown company name | Add company alias to Clients table, update Company Raw |
| `UNMATCHED — REVIEW` | Company name retry loop exhausted | Manually match; update Calls Log Client field |

### 3. Replay the call
The full transcript is stored in Calls Log → **Transcript** field.

To replay:
1. In n8n → open workflow **SOPBot Main**
2. Click **Test workflow** → paste the original webhook payload
3. In the payload, use the **same `call.id`** (so idempotency check passes — first delete or update the Error record's Status to `Replaying` so the dedup query skips it)
4. Execute

### 4. Verify
- New Status = Complete
- Google Doc created in client's Drive folder
- Notification email sent

### 5. Clean up
- If a duplicate record was created during replay, delete it
- Update original record Status = Complete if needed
