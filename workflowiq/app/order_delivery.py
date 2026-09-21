"""Bridges a WorkflowIQ run to the pending Supabase order it fulfils, and
emails the finished PDF to the customer via SMTP once done.

A WorkflowIQ purchase creates a "Pending" row in Supabase's workflowiq_runs
table (see payments/app/fulfillment.py::_write_workflowiq_run). This module
lets the operator pick that pending order in the UI, then on completion
marks it "Complete" and emails the customer their report - closing the loop
that was previously missing entirely (purchase -> nothing).

Uses plain SMTP (support@thesopbot.com, hosted on SiteGround) rather than
GHL - GHL's shared sub-account is used by a different project, so sending
customer emails through it would mix that project's contacts with
SOPBot's paying customers. Port 587/STARTTLS specifically, not 465/SSL -
confirmed via a real test that the Hetzner host this runs on blocks
outbound 465 but allows 587."""
from __future__ import annotations
import os
from dataclasses import dataclass

SMTP_HOST = os.environ.get("SMTP_HOST", "mail.thesopbot.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "support@thesopbot.com")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")


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
    """Sends the finished PDF to the customer as a real email attachment
    via SMTP - no upload/hosting step needed, unlike GHL's URL-only
    attachments field."""
    if not SMTP_PASSWORD:
        raise RuntimeError("SMTP_PASSWORD not configured - cannot email report")

    import smtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["Subject"] = "Your WorkflowIQ report is ready"
    msg["From"] = SMTP_USER
    msg["To"] = contact_email
    msg.set_content("Your WorkflowIQ process optimization report is attached.")
    msg.add_alternative(
        "<p>Your WorkflowIQ process optimization report is ready - see the attached PDF.</p>",
        subtype="html",
    )

    with open(pdf_path, "rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="pdf",
            filename=os.path.basename(pdf_path),
        )

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)
