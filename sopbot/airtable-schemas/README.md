# SOPBot Airtable Schema

Base name: **DadaAI SOPBot** (one base, two tables)

---

## Table 1: Clients

| Field Name        | Type            | Notes                                   |
|-------------------|-----------------|-----------------------------------------|
| Client Name       | Single line text| Primary field                           |
| Company Raw       | Single line text| Exact name as spoken (for matching)     |
| Industry          | Single select   |                                         |
| Contact Email     | Email           |                                         |
| Vapi Phone Number | Single line text| Assigned inbound number                 |
| Drive Folder ID   | Single line text| Google Drive client folder ID           |
| Status            | Single select   | Active / Inactive                       |
| Created           | Created time    |                                         |
| Calls             | Link to Calls Log |                                       |

---

## Table 2: Calls Log

| Field Name          | Type              | Notes                                                   |
|---------------------|-------------------|---------------------------------------------------------|
| Call ID             | Single line text  | Vapi call_id — **unique, used for idempotency**         |
| Client              | Link to Clients   |                                                         |
| Employee Name       | Single line text  |                                                         |
| Process Name        | Single line text  | Extracted by Claude                                     |
| Call Timestamp      | Date/time         | UTC                                                     |
| Duration Seconds    | Number            |                                                         |
| Transcript          | Long text         | Full call transcript (Confidential — PII)               |
| SOP Doc URL         | URL               | Google Doc link                                         |
| Status              | Single select     | Processing / Complete / Error / Duplicate               |
| Error Detail        | Long text         | Populated on error for replay                           |
| Company Raw         | Single line text  | Name as spoken — for matching / review                  |
| Notification Sent   | Checkbox          |                                                         |
| Created             | Created time      |                                                         |

**Idempotency rule:** Before creating a record, n8n checks if `Call ID` already exists.
If found → set Status = Duplicate and stop. Never create a second SOP.
