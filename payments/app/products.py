"""Product catalog for SOPBot packs and WorkflowIQ reports.

Prices are in cents (Square's Money type uses the smallest currency unit).
This is the single source of truth for pricing - checkout, webhook
fulfillment, and any future dashboard display should all read from here
rather than hardcoding amounts in multiple places.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    id: str
    name: str
    description: str
    amount_cents: int
    category: str  # "sopbot_pack" | "workflowiq_report"
    stripe_price_id: str  # real live-mode Stripe Price, referenced directly at checkout
    sop_credits: int | None = None  # only set for sopbot_pack products


CATALOG: dict[str, Product] = {
    "sopbot_single": Product(
        id="sopbot_single",
        name="SOPBot | single unit",
        description="1 SOP call credit",
        amount_cents=3700,
        category="sopbot_pack",
        stripe_price_id="price_1UD7DrGZSzCmqf6TtE40Rfpv",
        sop_credits=1,
    ),
    "sopbot_5pack": Product(
        id="sopbot_5pack",
        name="SOPBot | 5-pack",
        description="5 SOP call credits",
        amount_cents=12500,
        category="sopbot_pack",
        stripe_price_id="price_1UD7EoGZSzCmqf6Tez1UNOPb",
        sop_credits=5,
    ),
    "sopbot_15pack": Product(
        id="sopbot_15pack",
        name="SOPBot | 15-pack",
        description="15 SOP call credits",
        amount_cents=30000,
        category="sopbot_pack",
        stripe_price_id="price_1UD7FjGZSzCmqf6T4RdXmtEq",
        sop_credits=15,
    ),
    "workflowiq_up_to_5": Product(
        id="workflowiq_up_to_5",
        name="WorkflowIQ | Up to 5 SOPs",
        description="Process optimization report for up to 5 SOPs",
        amount_cents=9700,
        category="workflowiq_report",
        stripe_price_id="price_1UD7JaGZSzCmqf6TATUQWaJy",
    ),
    "workflowiq_6_to_15": Product(
        id="workflowiq_6_to_15",
        name="WorkflowIQ | 6-15 SOPs",
        description="Process optimization report for 6-15 SOPs",
        amount_cents=19700,
        category="workflowiq_report",
        stripe_price_id="price_1UD7KhGZSzCmqf6TqAQWdpTr",
    ),
    "workflowiq_16_to_30": Product(
        id="workflowiq_16_to_30",
        name="WorkflowIQ | 16-30 SOPs",
        description="Process optimization report for 16-30 SOPs",
        amount_cents=34700,
        category="workflowiq_report",
        stripe_price_id="price_1UD7LaGZSzCmqf6TIuB0FeU1",
    ),
}


def get_product(product_id: str) -> Product:
    if product_id not in CATALOG:
        raise ValueError(f"Unknown product id: {product_id}")
    return CATALOG[product_id]
