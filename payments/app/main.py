"""Payment service: Square Checkout for SOPBot packs and WorkflowIQ reports.

Flow:
  1. POST /checkout/<product_id> -> creates a Square Payment Link, returns
     the hosted checkout URL to redirect the buyer to.
  2. Square calls POST /webhook/square when payment completes.
  3. On a verified, completed payment, fulfillment is attempted (create/
     update the Airtable account record with credits). If Airtable is
     unavailable, the event is queued to disk instead of dropped, so a
     paid order is never silently lost - see fulfillment.py.
"""
from __future__ import annotations
import os
import uuid
import logging

from flask import Flask, request, jsonify, redirect
from square.client import Square, SquareEnvironment

from app.products import get_product, CATALOG
from app.fulfillment import fulfill_order, verify_webhook_signature

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("payments")

app = Flask(__name__)

SQUARE_ACCESS_TOKEN = os.environ["SQUARE_ACCESS_TOKEN"]
SQUARE_LOCATION_ID = os.environ["SQUARE_LOCATION_ID"]
SQUARE_ENVIRONMENT = os.environ.get("SQUARE_ENVIRONMENT", "sandbox")  # "sandbox" | "production"
SQUARE_WEBHOOK_SIGNATURE_KEY = os.environ.get("SQUARE_WEBHOOK_SIGNATURE_KEY", "")
PUBLIC_BASE_URL = os.environ["PUBLIC_BASE_URL"]  # e.g. https://pay.dadaai... - used for redirect URLs

square_client = Square(
    token=SQUARE_ACCESS_TOKEN,
    environment=SquareEnvironment.SANDBOX if SQUARE_ENVIRONMENT == "sandbox" else SquareEnvironment.PRODUCTION,
)


@app.route("/health")
def health():
    return jsonify(status="ok")


@app.route("/checkout/<product_id>", methods=["POST"])
def create_checkout(product_id: str):
    """Create a Square Payment Link for the requested product and redirect
    the buyer to Square's hosted checkout page."""
    try:
        product = get_product(product_id)
    except ValueError:
        return jsonify(error=f"Unknown product: {product_id}"), 404

    buyer_email = request.args.get("email", "")
    idempotency_key = str(uuid.uuid4())

    kwargs = dict(
        idempotency_key=idempotency_key,
        quick_pay={
            "name": product.name,
            "price_money": {
                "amount": product.amount_cents,
                "currency": "USD",
            },
            "location_id": SQUARE_LOCATION_ID,
        },
        checkout_options={
            "redirect_url": f"{PUBLIC_BASE_URL}/checkout/success?product={product.id}",
            "ask_for_shipping_address": False,
        },
        # payment_note carries the product id through to the webhook payload
        # (see payment.note in fulfillment._extract_order_details), since
        # Quick Pay links don't support arbitrary order-level metadata.
        payment_note=product.id,
    )
    if buyer_email:
        kwargs["pre_populated_data"] = {"buyer_email": buyer_email}

    try:
        result = square_client.checkout.payment_links.create(**kwargs)
    except Exception as e:
        log.error("Square checkout creation failed: %s", e)
        return jsonify(error="checkout_creation_failed", details=str(e)), 502

    if result.errors:
        log.error("Square checkout creation returned errors: %s", result.errors)
        return jsonify(error="checkout_creation_failed", details=[str(e) for e in result.errors]), 502

    payment_link = result.payment_link
    log.info("Created payment link %s for product %s", payment_link.id, product_id)
    return redirect(payment_link.url, code=303)


@app.route("/checkout/success")
def checkout_success():
    """Landing page after a successful redirect from Square. Fulfillment
    itself happens via the webhook, not this redirect - a redirect can be
    skipped/closed by the buyer's browser, a webhook cannot."""
    product_id = request.args.get("product", "")
    return jsonify(
        message="Payment received - your order is being processed. "
                "You'll receive access details shortly.",
        product=product_id,
    )


@app.route("/webhook/square", methods=["POST"])
def square_webhook():
    """Square's source of truth for payment completion. Verifies the
    signature before trusting the payload - webhook endpoints are public
    URLs and must not act on unverified requests."""
    raw_body = request.get_data(as_text=True)
    signature = request.headers.get("x-square-hmacsha256-signature", "")
    webhook_url = f"{PUBLIC_BASE_URL}/webhook/square"

    if SQUARE_WEBHOOK_SIGNATURE_KEY and not verify_webhook_signature(
        SQUARE_WEBHOOK_SIGNATURE_KEY, webhook_url, raw_body, signature
    ):
        log.warning("Rejected webhook with invalid signature")
        return jsonify(error="invalid_signature"), 401

    event = request.get_json(force=True, silent=True) or {}
    event_type = event.get("type", "")

    if event_type != "payment.updated":
        return jsonify(status="ignored", type=event_type), 200

    payment = event.get("data", {}).get("object", {}).get("payment", {})
    if payment.get("status") != "COMPLETED":
        return jsonify(status="ignored", payment_status=payment.get("status")), 200

    fulfill_order(payment)
    return jsonify(status="processed"), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
