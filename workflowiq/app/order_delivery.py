"""Bridges a WorkflowIQ run to the pending Supabase order it fulfils, and
emails the finished PDF to the customer via GHL once done.

A WorkflowIQ purchase creates a "Pending" row in Supabase's workflowiq_runs
table (see payments/app/fulfillment.py::_write_workflowiq_run). This module
lets the operator pick that pending order in the UI, then on completion
marks it "Complete" and emails the customer their report - closing the loop
that was previously missing entirely (purchase -> nothing).
"""
from __future__ import annotations
import os
from dataclasses import dataclass

GHL_API_TOKEN = os.environ.get("GHL_API_TOKEN", "")
GHL_LOCATION_ID = os.environ.get("GHL_LOCATION_ID", "")


@dataclass
class PendingOrder:
    id: str
    contact_email: str
    report_type: str
    payment_id: str


def _supabase_client():
    from supabase import create_client
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


def list_pending_orders() -> list[PendingOrder]:
    """Orders awaiting fulfilment, newest first. Used to populate the
    operator's order picker so a run can be tied to the purchase it's for."""
    client = _supabase_client()
    res = (
        client.table("workflowiq_runs")
        .select("id, contact_email, report_type, payment_id")
        .eq("status", "Pending")
        .order("run_timestamp", desc=True)
        .execute()
    )
    return [PendingOrder(**r) for r in res.data]


def mark_order_complete(
    order_id: str,
    process_names: str,
    sops_analysed: int,
    automation_opportunities_found: int,
    pdf_filename: str,
) -> None:
    client = _supabase_client()
    client.table("workflowiq_runs").update({
        "status": "Complete",
        "process_names": process_names,
        "sops_analysed": sops_analysed,
        "automation_opportunities_found": automation_opportunities_found,
        "pdf_filename": pdf_filename,
    }).eq("id", order_id).execute()


def email_report_to_customer(contact_email: str, pdf_path: str) -> None:
    """Sends the finished PDF to the customer via GHL, same API this
    product already uses for every other customer-facing email (see the
    n8n Dwayne-notification nodes for the same pattern).

    GHL's /conversations/messages attachments field is a plain array of
    public HTTPS URLs (verified against GHL's official API docs - it does
    NOT accept base64 or file uploads), so the PDF is uploaded to Drive
    and shared first (see google_drive.reader.upload_pdf_public), then
    that URL is passed here."""
    if not (GHL_API_TOKEN and GHL_LOCATION_ID):
        raise RuntimeError("GHL_API_TOKEN/GHL_LOCATION_ID not configured - cannot email report")

    import requests
    from app.google_drive.reader import upload_pdf_public

    pdf_url = upload_pdf_public(pdf_path, os.path.basename(pdf_path))

    headers = {
        "Authorization": f"Bearer {GHL_API_TOKEN}",
        "Version": "2021-07-28",
        "Content-Type": "application/json",
    }

    upsert = requests.post(
        "https://services.leadconnectorhq.com/contacts/upsert",
        headers=headers,
        json={"locationId": GHL_LOCATION_ID, "email": contact_email, "source": "WorkflowIQ report delivery"},
        timeout=15,
    )
    upsert.raise_for_status()
    contact_id = upsert.json()["contact"]["id"]

    send = requests.post(
        "https://services.leadconnectorhq.com/conversations/messages",
        headers=headers,
        json={
            "type": "Email",
            "contactId": contact_id,
            "subject": "Your WorkflowIQ report is ready",
            "html": "<p>Your WorkflowIQ process optimization report is ready - see the attached PDF.</p>",
            "attachments": [pdf_url],
        },
        timeout=30,
    )
    send.raise_for_status()
