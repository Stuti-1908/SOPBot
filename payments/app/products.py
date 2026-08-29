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
    sop_credits: int | None = None  # only set for sopbot_pack products


CATALOG: dict[str, Product] = {
    "sopbot_starter": Product(
        id="sopbot_starter",
        name="SOPBot Starter Pack",
        description="5 SOP call credits",
        amount_cents=19900,
        category="sopbot_pack",
        sop_credits=5,
    ),
    "sopbot_team": Product(
        id="sopbot_team",
        name="SOPBot Team Pack",
        description="15 SOP call credits",
        amount_cents=49900,
        category="sopbot_pack",
        sop_credits=15,
    ),
    "sopbot_department": Product(
        id="sopbot_department",
        name="SOPBot Department Pack",
        description="30 SOP call credits",
        amount_cents=89900,
        category="sopbot_pack",
        sop_credits=30,
    ),
    "sopbot_topup": Product(
        id="sopbot_topup",
        name="SOPBot À la Carte Top-up",
        description="1 additional SOP call credit",
        amount_cents=4900,
        category="sopbot_pack",
        sop_credits=1,
    ),
    "workflowiq_single": Product(
        id="workflowiq_single",
        name="WorkflowIQ Single-SOP Report",
        description="Process optimization report for 1 SOP",
        amount_cents=9900,
        category="workflowiq_report",
    ),
    "workflowiq_multi": Product(
        id="workflowiq_multi",
        name="WorkflowIQ Multi-SOP Report",
        description="Process optimization report for up to 8 SOPs",
        amount_cents=24900,
        category="workflowiq_report",
    ),
    "workflowiq_rerun": Product(
        id="workflowiq_rerun",
        name="WorkflowIQ Report Re-run",
        description="Updated report after process changes",
        amount_cents=4900,
        category="workflowiq_report",
    ),
}


def get_product(product_id: str) -> Product:
    if product_id not in CATALOG:
        raise ValueError(f"Unknown product id: {product_id}")
    return CATALOG[product_id]
