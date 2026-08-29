"""Owner dashboard: token-gated view of SOP credits, completed SOPs, and
WorkflowIQ report history. Access is via a per-account magic-link token
(?token=...) instead of a login system - matches how the buyer's journey
spec describes instant post-purchase access with no signup step."""
from __future__ import annotations
import os
import streamlit as st

from app.data import get_account_by_token, get_completed_sops, get_workflowiq_runs

CALL_IN_NUMBER = os.getenv("SOPBOT_CALL_NUMBER", "+1 903-626-7053")


def render_ui() -> None:
    token = st.query_params.get("token", "")

    if not token:
        _render_token_prompt()
        return

    account = get_account_by_token(token)
    if account is None:
        st.error("This dashboard link isn't valid. Check the link from your confirmation email, or contact support.")
        return

    _render_dashboard(account)


def _render_token_prompt() -> None:
    st.title("SOPBot Dashboard")
    st.write("This dashboard is accessed via your personal link, sent when you purchased a SOP pack.")
    st.write("If you've lost it, contact support and we'll resend it.")


def _render_dashboard(account) -> None:
    st.title(f"Welcome back, {account.client_name}")

    if account.status != "Active":
        st.warning(f"Account status: {account.status}. Contact support if this looks wrong.")

    # ── Pack usage ───────────────────────────────────────────────
    st.subheader("Your SOP pack")
    col1, col2, col3 = st.columns(3)
    col1.metric("Credits used", account.sop_credits_used)
    col2.metric("Credits remaining", account.sop_credits_remaining)
    col3.metric("Pack size", account.sop_pack_size)

    progress = account.sop_credits_used / account.sop_pack_size if account.sop_pack_size else 0
    st.progress(min(progress, 1.0))

    if account.sop_credits_remaining == 0:
        st.info("You're out of credits. Top up à la carte at $49/SOP, or step up to a bigger pack.")
    elif account.sop_credits_remaining <= 2:
        st.caption(f"Only {account.sop_credits_remaining} credit(s) left — consider topping up soon.")

    st.divider()

    # ── Call-in details ──────────────────────────────────────────
    st.subheader("Share with your team")
    st.write(f"**Call-in number:** {CALL_IN_NUMBER}")
    st.write(f"**Your PIN:** `{account.call_pin}` — employees enter this so their SOP lands in your dashboard automatically.")
    st.caption("Give employees the number, the PIN, and the prep sheet so they know what to expect before calling.")

    st.divider()

    # ── Completed SOPs ───────────────────────────────────────────
    st.subheader("Your SOP library")
    sops = get_completed_sops(account)

    if not sops:
        st.write("No completed SOPs yet. Once your team starts calling, they'll show up here automatically.")
    else:
        for sop in sorted(sops, key=lambda s: s.call_timestamp, reverse=True):
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.write(f"**{sop.process_name}**")
                    st.caption(f"Documented by {sop.employee_name} · {sop.call_timestamp.strftime('%b %d, %Y')}")
                with c2:
                    if sop.sop_doc_url:
                        st.link_button("View SOP", sop.sop_doc_url, use_container_width=True)

    # ── Upsell: WorkflowIQ ───────────────────────────────────────
    if len(sops) >= 2:
        st.divider()
        with st.container(border=True):
            st.subheader("See where you're losing hours every week")
            st.write(
                f"You've documented {len(sops)} processes. Run a WorkflowIQ report to find "
                "automation opportunities across them — scored by time saved, effort, and impact."
            )
            wiq_url = os.getenv("WORKFLOWIQ_URL", "#")
            st.link_button("Run a WorkflowIQ report →", wiq_url, type="primary")

    # ── WorkflowIQ report history ────────────────────────────────
    runs = get_workflowiq_runs(account)
    if runs:
        st.divider()
        st.subheader("Your WorkflowIQ reports")
        for run in sorted(runs, key=lambda r: r.run_timestamp, reverse=True):
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.write(f"**{run.process_names}** ({run.report_type})")
                    st.caption(
                        f"{run.run_timestamp.strftime('%b %d, %Y')} · "
                        f"{run.automation_opportunities_found} automation opportunities found"
                    )
                with c2:
                    st.caption(run.pdf_filename)
