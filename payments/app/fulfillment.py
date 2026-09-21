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

    try:
        if product and product.category == "workflowiq_report":
            _write_workflowiq_run(order, product)
        else:
            account = _write_to_supabase(order)
            _notify_customer_welcome(order, account)
        log.info("Order %s fulfilled directly in Supabase", order["payment_id"])
    except Exception as e:
        log.error("Supabase fulfillment failed (%s) - queueing order %s for replay", e, order["payment_id"])
        _queue_order(order)

    if product and product.category == "workflowiq_report":
        _notify_workflowiq_order(order, product)


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


def _write_workflowiq_run(order: dict, product) -> None:
    """Record a pending WorkflowIQ order so staff can see it needs running and
    the dashboard can show "Pending" instead of nothing. Mirrors _write_to_supabase's
    match-by-email approach, but client_id is optional here - a first-time
    WorkflowIQ buyer may not have a clients row yet (see schema migration
    that dropped client_id's NOT NULL constraint on workflowiq_runs)."""
    if not (SUPABASE_URL and SUPABASE_SERVICE_KEY):
        raise RuntimeError("Supabase env vars not fully configured")

    from supabase import create_client
    client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

    existing = (
        client.table("clients")
        .select("id")
        .eq("contact_email", order["buyer_email"])
        .limit(1)
        .execute()
    )
    client_id = existing.data[0]["id"] if existing.data else None

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

    import requests
    try:
        requests.post(
            CUSTOMER_WELCOME_WEBHOOK_URL,
            headers={"x-webhook-secret": CUSTOMER_WELCOME_WEBHOOK_SECRET, "Content-Type": "application/json"},
            json={
                "buyer_email": order["buyer_email"],
                "from_email": WELCOME_EMAIL_FROM,
                "dashboard_token": account.get("dashboard_token", ""),
                "call_pin": account.get("call_pin", ""),
                "call_number": SOPBOT_CALL_NUMBER,
            },
            timeout=10,
        )
    except Exception as e:
        log.error("Customer welcome email failed for %s: %s", order["payment_id"], e)


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


def _queue_order(order: dict) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(QUEUE_PATH, "a") as f:
        f.write(json.dumps(order) + "\n")


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
