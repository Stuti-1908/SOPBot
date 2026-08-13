# Runbook: Onboarding a New Client onto SOPBot

**Who:** Dwayne or Stuti  
**Time required:** ~20 minutes  
**Pre-requisites:** Access to Airtable, Vapi dashboard, Google Drive (service account already shared)

---

## Steps

### 1. Create client record in Airtable
- Open base **DadaAI SOPBot** → Table **Clients**
- Create new record:
  - **Client Name:** Official company name
  - **Company Raw:** Exactly as the employee will say it on the call
  - **Industry:** Select appropriate value
  - **Contact Email:** Primary contact
  - **Status:** Active

### 2. Create Google Drive folder
- In Google Drive → `SOPBot Clients/` → New folder named `[ClientName]`
- Share the folder with the service account email (found in `gcp_sa.json` → `client_email`)
- Copy the folder ID from the URL: `drive.google.com/drive/folders/[FOLDER_ID]`
- Paste **Drive Folder ID** into the Airtable Clients record

### 3. Copy SOP template for client
- In Drive → `SOPBot Templates/` → right-click `SOP Template v1` → Make a copy
- Move copy into `SOPBot Clients/[ClientName]/`
- Note the new doc's ID for n8n (it reads this template before filling)

### 4. Configure Vapi inbound number
- Open Vapi dashboard → Phone Numbers → assign or purchase a number
- Set the inbound assistant to **SOPBot Production**
- Note the number and paste into Airtable **Vapi Phone Number** field

### 5. Brief the client
- Send onboarding email (GHL template: "SOPBot Client Welcome")
- Include: the phone number, what to expect, that they should state their company name clearly at the start

### 6. Test the flow
- Call the number from your own phone
- Say the client's company name when prompted
- Verify:
  - Airtable Calls Log gets a new record with Status = Complete
  - Google Doc is created in the client's Drive folder
  - Notification email arrives in Dwayne + Stuti inboxes

---

## Rollback
If the test call fails:
- Check Airtable Calls Log → Error Detail column
- Check n8n execution log for the failed run
- See runbook: `error_replay.md`
