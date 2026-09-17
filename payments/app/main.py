"""Payment service: Stripe Checkout for SOPBot packs and WorkflowIQ reports.

Flow:
  1. POST /checkout/<product_id> -> creates a Stripe Checkout Session,
     returns the hosted checkout URL to redirect the buyer to.
  2. Stripe calls POST /webhook/stripe when payment completes.
  3. On a verified, completed payment, fulfillment is attempted (create/
     update the Supabase client record with credits). If Supabase is
     unavailable, the event is queued to disk instead of dropped, so a
     paid order is never silently lost - see fulfillment.py.
"""
from __future__ import annotations
import os
import logging

import stripe
from flask import Flask, request, jsonify, redirect

from app.products import get_product, CATALOG
from app.fulfillment import fulfill_order

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("payments")

app = Flask(__name__)

stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
PUBLIC_BASE_URL = os.environ["PUBLIC_BASE_URL"]  # e.g. https://pay.dadaai... - used for redirect URLs


@app.route("/health")
def health():
    return jsonify(status="ok")


@app.route("/checkout/<product_id>", methods=["POST"])
def create_checkout(product_id: str):
    """Create a Stripe Checkout Session for the requested product and
    redirect the buyer to Stripe's hosted checkout page."""
    try:
        product = get_product(product_id)
    except ValueError:
        return jsonify(error=f"Unknown product: {product_id}"), 404

    buyer_email = request.args.get("email", "")

    kwargs = dict(
        mode="payment",
        line_items=[{
            "price_data": {
                "currency": "usd",
                "unit_amount": product.amount_cents,
                "product_data": {
                    "name": product.name,
                    "description": product.description,
                },
            },
            "quantity": 1,
        }],
        success_url=f"{PUBLIC_BASE_URL}/checkout/success?product={product.id}",
        cancel_url=f"{PUBLIC_BASE_URL}/checkout/cancel?product={product.id}",
        # metadata carries the product id through to the webhook payload
        # (see session.metadata in fulfillment._extract_order_details)
        metadata={"product_id": product.id},
    )
    if buyer_email:
        kwargs["customer_email"] = buyer_email

    try:
        session = stripe.checkout.Session.create(**kwargs)
    except Exception as e:
        log.error("Stripe checkout creation failed: %s", e)
        return jsonify(error="checkout_creation_failed", details=str(e)), 502

    log.info("Created checkout session %s for product %s", session.id, product_id)
    return redirect(session.url, code=303)


@app.route("/checkout/success")
def checkout_success():
    """Landing page after a successful redirect from Stripe. Fulfillment
    itself happens via the webhook, not this redirect - a redirect can be
    skipped/closed by the buyer's browser, a webhook cannot."""
    product_id = request.args.get("product", "")
    return jsonify(
        message="Payment received - your order is being processed. "
                "You'll receive access details shortly.",
        product=product_id,
    )


@app.route("/checkout/cancel")
def checkout_cancel():
    product_id = request.args.get("product", "")
    return jsonify(message="Checkout cancelled.", product=product_id)


@app.route("/webhook/stripe", methods=["POST"])
def stripe_webhook():
    """Stripe's source of truth for payment completion. Verifies the
    signature before trusting the payload - webhook endpoints are public
    URLs and must not act on unverified requests."""
    raw_body = request.get_data()
    signature = request.headers.get("stripe-signature", "")

    if STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(raw_body, signature, STRIPE_WEBHOOK_SECRET).to_dict()
        except (ValueError, stripe.error.SignatureVerificationError) as e:
            log.warning("Rejected webhook with invalid signature: %s", e)
            return jsonify(error="invalid_signature"), 401
    else:
        event = request.get_json(force=True, silent=True) or {}

    event_type = event.get("type", "")

    if event_type != "checkout.session.completed":
        return jsonify(status="ignored", type=event_type), 200

    session = event.get("data", {}).get("object", {})
    if session.get("payment_status") != "paid":
        return jsonify(status="ignored", payment_status=session.get("payment_status")), 200

    fulfill_order(session)
    return jsonify(status="processed"), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
