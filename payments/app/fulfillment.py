"""Order fulfillment: turn a completed Stripe payment into Supabase account
state (SOP credits granted, or a WorkflowIQ report unlocked).

A paid order must never be silently dropped. If the Supabase write fails
for any reason, the order is appended to a local queue file instead of
being lost, and can be replayed once Supabase is available again via
replay_queued_orders().
"""
from __future__ import annotations
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from app.products import get_product

log = logging.getLogger("payments.fulfillment")

QUEUE_PATH = Path(os.environ.get("FULFILLMENT_QUEUE_PATH", "/app/data/pending_orders.jsonl"))
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
WORKFLOWIQ_ORDER_WEBHOOK_URL = os.environ.get("WORKFLOWIQ_ORDER_WEBHOOK_URL", "")
WORKFLOWIQ_ORDER_WEBHOOK_SECRET = os.environ.get("WORKFLOWIQ_ORDER_WEBHOOK_SECRET", "")
CUSTOMER_WELCOME_WEBHOOK_URL = os.environ.get("CUSTOMER_WELCOME_WEBHOOK_URL", "")
CUSTOMER_WELCOME_WEBHOOK_SECRET = os.environ.get("CUSTOMER_WELCOME_WEBHOOK_SECRET", "")
WELCOME_EMAIL_FROM = os.environ.get("WELCOME_EMAIL_FROM", "")
SOPBOT_CALL_NUMBER = os.environ.get("SOPBOT_CALL_NUMBER", "+1 903-626-7053")
FULFILLMENT_ALERT_WEBHOOK_URL = os.environ.get("FULFILLMENT_ALERT_WEBHOOK_URL", "")
FULFILLMENT_ALERT_WEBHOOK_SECRET = os.environ.get("FULFILLMENT_ALERT_WEBHOOK_SECRET", "")
REVOKE_ACCESS_WEBHOOK_URL = os.environ.get("REVOKE_ACCESS_WEBHOOK_URL", "")
REVOKE_ACCESS_WEBHOOK_SECRET = os.environ.get("REVOKE_ACCESS_WEBHOOK_SECRET", "")


def _extract_company_name(payment: dict) -> str:
    """Pulls the "company_name" custom field collected at checkout (see
    main.py's custom_fields on Session.create). This is the value the
    voice call flow will later match against by spoken company name, so
    it must be stored on clients.client_name exactly as the customer typed
    it here."""
    for field in payment.get("custom_fields") or []:
        if field.get("key") == "company_name":
            return (field.get("text") or {}).get("value", "") or ""
    return ""


def _extract_order_details(payment: dict) -> dict:
    """payment is a Stripe Checkout Session object (see main.py webhook
    handler, which passes session.to_dict())."""
    buyer_email = (payment.get("customer_details") or {}).get("email", "") or payment.get("customer_email", "") or ""
    product_id = (payment.get("metadata") or {}).get("product_id", "")
    return {
        "payment_id": payment.get("id"),
        "amount_cents": payment.get("amount_total", 0),
        "buyer_email": buyer_email,
        "company_name": _extract_company_name(payment),
        "product_id": product_id,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }


def fulfill_order(payment: dict) -> None:
    order = _extract_order_details(payment)
    log.info("Fulfilling order: %s", order)

    product = get_product(order["product_id"]) if order.get("product_id") else None
    workflowiq_account = None

    try:
        if product and product.category == "workflowiq_report":
            workflowiq_account = _write_workflowiq_run(order, product)
        else:
            account = _write_to_supabase(order)
            _notify_customer_welcome(order, account)
        log.info("Order %s fulfilled directly in Supabase", order["payment_id"])
    except Exception as e:
        log.error("Supabase fulfillment failed (%s) - queueing order %s for replay", e, order["payment_id"])
        _queue_order(order)
        # The on-disk queue is best-effort only - on Vercel's serverless
        # runtime the filesystem isn't guaranteed to persist between
        # invocations, so replay_queued_orders() may never see this order.
        # An immediate alert is the real safety net: staff can look up the
        # payment in Stripe's dashboard and fulfill it by hand if needed.
        _alert_fulfillment_failure(order, e)

    if product and product.category == "workflowiq_report":
        _notify_workflowiq_order(order, product)
        _notify_workflowiq_order_received(order, product, workflowiq_account)


def _write_to_supabase(order: dict) -> dict:
    """Returns the resulting clients row (dashboard_token/call_pin included)
    so the caller can send the customer their access details - see
    _notify_customer_welcome."""
    if not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
        raise RuntimeError("Supabase env vars not fully configured")

    from supabase import create_client
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    product = get_product(order["product_id"]) if order.get("product_id") else None
    sop_credits = product.sop_credits if product and product.sop_credits else 0

    existing = (
        client.table("clients")
        .select("id, sop_pack_size, client_name, dashboard_token, call_pin")
        .eq("contact_email", order["buyer_email"])
        .limit(1)
        .execute()
    )
    if existing.data:
        client_id = existing.data[0]["id"]
        new_pack_size = int(existing.data[0].get("sop_pack_size", 0) or 0) + sop_credits
        update = {"sop_pack_size": new_pack_size, "status": "Active"}
        # Only overwrite client_name if it isn't set yet - a repeat top-up
        # shouldn't blank it out if this order's field was left empty.
        if order.get("company_name") and not existing.data[0].get("client_name"):
            update["client_name"] = order["company_name"]
        res = client.table("clients").update(update).eq("id", client_id).execute()
        return res.data[0]
    else:
        import secrets
        res = client.table("clients").insert({
            "contact_email": order["buyer_email"],
            "client_name": order.get("company_name", ""),
            "status": "Active",
            "sop_pack_size": sop_credits,
            "sop_credits_used": 0,
            "dashboard_token": secrets.token_urlsafe(16),
            "call_pin": f"{secrets.randbelow(10000):04d}",
        }).execute()
        return res.data[0]


def _write_workflowiq_run(order: dict, product) -> dict | None:
    """Record a pending WorkflowIQ order so staff can see it needs running and
    the dashboard can show "Pending" instead of nothing. Mirrors _write_to_supabase's
    match-by-email approach, but client_id is optional here - a first-time
    WorkflowIQ buyer may not have a clients row yet (see schema migration
    that dropped client_id's NOT NULL constraint on workflowiq_runs).

    Returns the matched clients row (with dashboard_token) if one exists, so
    the order-received email can link to a real dashboard - or None for a
    first-time WorkflowIQ-only buyer with no account yet."""
    if not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
        raise RuntimeError("Supabase env vars not fully configured")

    from supabase import create_client
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    existing = (
        client.table("clients")
        .select("id, dashboard_token")
        .eq("contact_email", order["buyer_email"])
        .limit(1)
        .execute()
    )
    account = existing.data[0] if existing.data else None
    client_id = account["id"] if account else None

    client.table("workflowiq_runs").insert({
        "client_id": client_id,
        "process_names": "",
        "sops_analysed": 0,
        "automation_opportunities_found": 0,
        "pdf_filename": "",
        "report_type": product.name,
        "status": "Pending",
        "contact_email": order["buyer_email"],
        "payment_id": order["payment_id"],
    }).execute()

    return account


_TEMPLATES_DIR = Path(__file__).parent / "email_templates"


def _render_welcome_email_html(account: dict) -> str:
    """Renders the branded welcome email in Python rather than building it
    as an n8n expression string - the n8n JS-expression approach broke
    repeatedly on quote/escaping collisions between the outer expression
    string and the HTML's own quoted attributes. Rendering here means n8n
    just forwards whatever HTML it's given, no string surgery involved."""
    template = (_TEMPLATES_DIR / "welcome_email.html").read_text(encoding="utf-8")
    dashboard_url = f"https://dashboard.thesopbot.com/?token={account.get('dashboard_token', '')}"
    return template.format(
        call_number=SOPBOT_CALL_NUMBER,
        call_pin=account.get("call_pin", ""),
        dashboard_url=dashboard_url,
    )


def _notify_customer_welcome(order: dict, account: dict) -> None:
    """Sends the buyer their dashboard link/PIN right after a SOPBot pack
    purchase. Without this, a paying customer has no way to find their
    dashboard - the checkout success page promises "access details
    shortly" but nothing used to deliver on that promise until now.

    Best-effort: failure here must never undo the Supabase write above,
    since the account itself is already correctly provisioned regardless
    of whether this email goes out."""
    if not CUSTOMER_WELCOME_WEBHOOK_URL:
        log.warning("CUSTOMER_WELCOME_WEBHOOK_URL not configured - skipping welcome email for %s", order["payment_id"])
        return

    html = _render_welcome_email_html(account)

    import requests
    try:
        requests.post(
            CUSTOMER_WELCOME_WEBHOOK_URL,
            headers={"x-webhook-secret": CUSTOMER_WELCOME_WEBHOOK_SECRET, "Content-Type": "application/json"},
            json={
                "buyer_email": order["buyer_email"],
                "from_email": WELCOME_EMAIL_FROM,
                "subject": "Welcome to SOPBot - your dashboard is ready",
                "html": html,
            },
            timeout=10,
        )
    except Exception as e:
        log.error("Customer welcome email failed for %s: %s", order["payment_id"], e)


def _render_order_received_email_html(order: dict, product, account: dict | None) -> str:
    """Renders the WorkflowIQ order-received email. Sets a 24-48 hour
    delivery expectation immediately at purchase time, since previously the
    customer's first email at all was the finished report itself - no
    acknowledgement that the order was received, which reads as a stalled
    or lost purchase if the operator takes a few hours to run it.

    The dashboard link/sentence is only included if this buyer already has
    a clients account (dashboard_token) - a first-time WorkflowIQ-only buyer
    has nothing to see on the dashboard today, so promising one would be a
    broken link in the email."""
    template = (_TEMPLATES_DIR / "order_received_email.html").read_text(encoding="utf-8")

    if account and account.get("dashboard_token"):
        dashboard_url = f"https://dashboard.thesopbot.com/?token={account['dashboard_token']}"
        dashboard_sentence = " You can also check on the status anytime from your dashboard."
        dashboard_button_block = (
            '<tr><td align="center" style="padding:16px 32px 8px;">'
            '<table role="presentation" cellpadding="0" cellspacing="0">'
            '<tr><td style="background-color:#C1602A; border-radius:4px;">'
            f'<a href="{dashboard_url}" style="display:inline-block; padding:14px 32px; '
            'font-family: Arial, Helvetica, sans-serif; font-size:15px; font-weight:600; '
            'color:#FAF6EF; text-decoration:none;">Check your dashboard</a>'
            "</td></tr></table></td></tr>"
        )
    else:
        dashboard_sentence = ""
        dashboard_button_block = ""

    return template.format(
        report_type=product.name,
        dashboard_sentence=dashboard_sentence,
        dashboard_button_block=dashboard_button_block,
    )


def _notify_workflowiq_order_received(order: dict, product, account: dict | None) -> None:
    """Sends the customer an acknowledgement email right after purchase,
    setting a 24-48 hour delivery expectation - closes the gap where a
    WorkflowIQ buyer previously got no confirmation at all until the
    finished report arrived, which could look like a stalled purchase.

    Best-effort: failure here must never block fulfillment - the order is
    already recorded in Supabase by _write_workflowiq_run regardless."""
    if not CUSTOMER_WELCOME_WEBHOOK_URL:
        log.warning("CUSTOMER_WELCOME_WEBHOOK_URL not configured - skipping order-received email for %s", order["payment_id"])
        return

    html = _render_order_received_email_html(order, product, account)

    import requests
    try:
        requests.post(
            CUSTOMER_WELCOME_WEBHOOK_URL,
            headers={"x-webhook-secret": CUSTOMER_WELCOME_WEBHOOK_SECRET, "Content-Type": "application/json"},
            json={
                "buyer_email": order["buyer_email"],
                "from_email": WELCOME_EMAIL_FROM,
                "subject": "We've received your WorkflowIQ request",
                "html": html,
            },
            timeout=10,
        )
    except Exception as e:
        log.error("WorkflowIQ order-received email failed for %s: %s", order["payment_id"], e)


def _notify_workflowiq_order(order: dict, product) -> None:
    """Best-effort alert to staff that a WorkflowIQ order needs to be run
    manually in the internal tool (see workflowiq/app/ui.py). Failure here
    must never block fulfillment - the order is already recorded in Supabase
    by _write_workflowiq_run regardless of whether this notification succeeds."""
    if not WORKFLOWIQ_ORDER_WEBHOOK_URL:
        log.warning("WORKFLOWIQ_ORDER_WEBHOOK_URL not configured - skipping staff notification for order %s", order["payment_id"])
        return

    import requests
    try:
        requests.post(
            WORKFLOWIQ_ORDER_WEBHOOK_URL,
            headers={"x-webhook-secret": WORKFLOWIQ_ORDER_WEBHOOK_SECRET, "Content-Type": "application/json"},
            json={
                "product_name": product.name,
                "company_name": order.get("company_name", ""),
                "buyer_email": order["buyer_email"],
                "payment_id": order["payment_id"],
            },
            timeout=10,
        )
    except Exception as e:
        log.error("WorkflowIQ order notification failed for %s: %s", order["payment_id"], e)


def revoke_client_access(buyer_email: str, reason: str) -> None:
    """Called when Stripe reports a refund or dispute (see main.py's
    /webhook/stripe handler for charge.refunded / charge.dispute.created).

    Updates Supabase directly (this service already has that dependency),
    and fires a webhook so n8n can update the matching Airtable Clients
    row's Status field too - the voice pipeline's Company Router primarily
    gates on Airtable, not Supabase, so both must be updated or a refunded
    customer could still successfully call in and consume credits."""
    if SUPABASE_URL and SUPABASE_SERVICE_KEY:
        try:
            from supabase import create_client
            client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
            client.table("clients").update({"status": "Refunded"}).eq("contact_email", buyer_email).execute()
            log.info("Revoked Supabase access for %s (%s)", buyer_email, reason)
        except Exception as e:
            log.error("Failed to revoke Supabase access for %s: %s", buyer_email, e)
    else:
        log.warning("Supabase env vars not configured - cannot revoke access for %s", buyer_email)

    if not REVOKE_ACCESS_WEBHOOK_URL:
        log.warning("REVOKE_ACCESS_WEBHOOK_URL not configured - Airtable Status not updated for %s", buyer_email)
        return

    import requests
    try:
        requests.post(
            REVOKE_ACCESS_WEBHOOK_URL,
            headers={"x-webhook-secret": REVOKE_ACCESS_WEBHOOK_SECRET, "Content-Type": "application/json"},
            json={"buyer_email": buyer_email, "reason": reason},
            timeout=10,
        )
    except Exception as e:
        log.error("Airtable access-revocation webhook failed for %s: %s", buyer_email, e)


def _alert_fulfillment_failure(order: dict, error: Exception) -> None:
    """Fires immediately when a Supabase write fails during fulfillment,
    since the on-disk queue this used to rely on alone doesn't reliably
    survive on Vercel's serverless runtime (see fulfill_order). Staff can
    look the payment up in Stripe's dashboard and fulfill it by hand."""
    if not FULFILLMENT_ALERT_WEBHOOK_URL:
        log.warning("FULFILLMENT_ALERT_WEBHOOK_URL not configured - cannot alert on fulfillment failure for %s", order["payment_id"])
        return

    import requests
    try:
        requests.post(
            FULFILLMENT_ALERT_WEBHOOK_URL,
            headers={"x-webhook-secret": FULFILLMENT_ALERT_WEBHOOK_SECRET, "Content-Type": "application/json"},
            json={
                "payment_id": order["payment_id"],
                "buyer_email": order["buyer_email"],
                "company_name": order.get("company_name", ""),
                "product_id": order.get("product_id", ""),
                "error": str(error),
            },
            timeout=10,
        )
    except Exception as e:
        log.error("Fulfillment-failure alert itself failed for %s: %s", order["payment_id"], e)


def _queue_order(order: dict) -> None:
    """Best-effort local backup of a failed order. On Vercel's serverless
    runtime this filesystem is usually unwritable/ephemeral, so this can
    legitimately fail - that must never crash the webhook handler (which
    would make Stripe think the whole request failed and retry it). The
    real safety net for a fulfillment failure is _alert_fulfillment_failure,
    called unconditionally regardless of whether this queue write works."""
    try:
        QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(QUEUE_PATH, "a") as f:
            f.write(json.dumps(order) + "\n")
    except Exception as e:
        log.warning("Could not write to local fulfillment queue (%s) - relying on the alert instead", e)


def replay_queued_orders() -> tuple[int, int]:
    """Attempt to fulfill every queued order against Supabase. Returns
    (succeeded, remaining). Call this once Supabase is confirmed working -
    not wired to any automatic trigger yet, run manually or via a small
    cron once needed."""
    if not QUEUE_PATH.exists():
        return (0, 0)

    lines = QUEUE_PATH.read_text().splitlines()
    still_pending = []
    succeeded = 0

    for line in lines:
        if not line.strip():
            continue
        order = json.loads(line)
        try:
            account = _write_to_supabase(order)
            _notify_customer_welcome(order, account)
            succeeded += 1
        except Exception as e:
            log.error("Replay failed for order %s: %s", order.get("payment_id"), e)
            still_pending.append(line)

    QUEUE_PATH.write_text("\n".join(still_pending) + ("\n" if still_pending else ""))
    return (succeeded, len(still_pending))
