# Employee Email Feature — Activation Checklist

Status: **Draft, not live.** Built 2026-09-14, imported into n8n as a separate
inactive workflow (`SOPBot Main (DRAFT - employee email feature)`, id
`fFboHgba81r265CZ`) so the live production workflow (`SOPBot Main`,
`u6Le9BsH3tYVCU2T`) is untouched and still running exactly as before.

## What this adds

After the existing owner-notification email fires, if the employee gave an
email address during the call, SOPBot now also:
1. Finds or creates a GHL contact for that employee (`12c. Upsert Employee
   Contact (GHL)`)
2. Emails them a link to their own SOP document (`12d. Employee Email
   (GHL)`)

If no email was captured, the call completes exactly as it does today - this
is additive, not a replacement for the existing owner-notification flow.

## Why it's not live yet

This could not be tested end-to-end from this session - there's no way to
place a real Vapi call or verify the full chain (Claude extraction →
Company Router match → GHL contact creation → email delivery) without a
live phone call reaching the real webhook. Importing straight over the
live production workflow would have replaced a working system with
untested code.

## What still needs to happen before this goes live

1. **Update the Vapi assistant script** to ask for the employee's email.
   Add this near the existing "first name" / "job title" questions in
   Section 1 of the call script (see the live script quoted earlier in
   project history):
   > "What's the best email to send you a copy of your SOP when we're
   > done?"

   This is a change inside the Vapi dashboard, not a file in this repo -
   someone with Vapi access needs to make it directly.

2. **Verify Claude actually extracts the email reliably.** The extraction
   prompt (`7. Claude Extraction` node) now includes `employee_email` in
   its schema, but this hasn't been tested against a real transcript that
   actually contains a spoken email address (people often say emails
   oddly out loud - "john dot smith at gmail dot com" - worth confirming
   Claude parses this into a valid address, not garbled text).

3. **Make one real test call** once the Vapi script is updated, saying a
   real email address you can check, and confirm:
   - The GHL contact gets created (check GHL contacts list)
   - The email actually arrives
   - The link in the email opens the correct SOP document
   - The owner still also gets their existing notification email (make
     sure nothing in the new branch broke the existing one)

4. **Only after that passes:** activate `SOPBot Main (DRAFT - employee
   email feature)` in the n8n UI, then deactivate and delete the old
   `SOPBot Main` (or keep it deactivated as a rollback point for a while
   first, then delete once confident).

5. **Export the final, tested version** and replace
   `sopbot/n8n-workflows/sopbot_main.json` in this repo (the draft
   currently lives alongside it as
   `sopbot_main_DRAFT_employee_email.json` - don't overwrite the
   known-working exported version until the draft is proven).

## Known limitation carried over from the existing GHL email nodes

GHL's Conversations API sends to a contact ID, not a raw email address -
this is why the new flow creates/finds a GHL contact first rather than
emailing directly. If GHL's account/plan has any contact-creation limits
or costs per contact, high call volume would create one new contact per
employee who provides an email - worth being aware of at scale, though
not a concern at current volume.
