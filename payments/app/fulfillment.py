"""Order fulfillment: turn a completed Square payment into Airtable account
state (SOP credits granted, or a WorkflowIQ report unlocked).

Airtable's API has been hitting PUBLIC_API_BILLING_LIMIT_EXCEEDED as of
2026-08-14 (see docs/runbooks/ - workspace billing limit). A paid order
must never be silently dropped because of that. If the Airtable write
fails for any reason, the order is appended to a local queue file instead
of being lost, and can be replayed once Airtable is available again via
replay_queued_orders().
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import requests

from app.products import get_product

log = logging.getLogger("payments.fulfillment")

QUEUE_PATH = Path(os.environ.get("FULFILLMENT_QUEUE_PATH", "/app/data/pending_orders.jsonl"))
AIRTABLE_API_TOKEN = os.environ.get("AIRTABLE_API_TOKEN", "")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID", "")
AIRTABLE_CLIENTS_TABLE = os.environ.get("AIRTABLE_CLIENTS_TABLE_ID", "")


def verify_webhook_signature(signature_key: str, notification_url: str, body: str, received_signature: str) -> bool:
    """Square's HMAC-SHA256 webhook signature scheme: sign
    (notification_url + raw_body) with the signature key, base64-encode,
    compare in constant time."""
    hmac_obj = hmac.new(signature_key.encode(), (notification_url + body).encode(), hashlib.sha256)
    expected = base64.b64encode(hmac_obj.digest()).decode()
    return hmac.compare_digest(expected, received_signature)


def _extract_order_details(payment: dict) -> dict:
    amount = payment.get("amount_money", {}).get("amount", 0)
    note = payment.get("note", "")  # product_id can be passed via order metadata
    buyer_email = payment.get("buyer_email_address", "")
    return {
        "payment_id": payment.get("id"),
        "amount_cents": amount,
        "buyer_email": buyer_email,
        "note": note,
        "received_at": datetime.now(timezone.utc).isoformat(),
    }


def fulfill_order(payment: dict) -> None:
    order = _extract_order_details(payment)
    log.info("Fulfilling order: %s", order)

    try:
        _write_to_airtable(order)
        log.info("Order %s fulfilled directly in Airtable", order["payment_id"])
    except Exception as e:
        log.error("Airtable fulfillment failed (%s) - queueing order %s for replay", e, order["payment_id"])
        _queue_order(order)


def _write_to_airtable(order: dict) -> None:
    if not (AIRTABLE_API_TOKEN and AIRTABLE_BASE_ID and AIRTABLE_CLIENTS_TABLE):
        raise RuntimeError("Airtable env vars not fully configured")

    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_CLIENTS_TABLE}"
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {AIRTABLE_API_TOKEN}", "Content-Type": "application/json"},
        json={"fields": {
            "Contact Email": order["buyer_email"],
            "Status": "Active",
            # SOP Pack Size / Credits fields populated once the schema
            # change from the multi-tenant plan is applied - see
            # docs/runbooks (Airtable schema evolution notes).
        }},
        timeout=15,
    )
    resp.raise_for_status()


def _queue_order(order: dict) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(QUEUE_PATH, "a") as f:
        f.write(json.dumps(order) + "\n")


def replay_queued_orders() -> tuple[int, int]:
    """Attempt to fulfill every queued order against Airtable. Returns
    (succeeded, remaining). Call this once Airtable's API is confirmed
    working again - not wired to any automatic trigger yet, run manually
    or via a small cron once needed."""
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
            _write_to_airtable(order)
            succeeded += 1
        except Exception as e:
            log.error("Replay failed for order %s: %s", order.get("payment_id"), e)
            still_pending.append(line)

    QUEUE_PATH.write_text("\n".join(still_pending) + ("\n" if still_pending else ""))
    return (succeeded, len(still_pending))
