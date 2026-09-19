"""Owner dashboard: token-gated view of SOP credits, completed SOPs, and
WorkflowIQ report history. Access is via a per-account magic-link token
(?token=...) instead of a login system - matches how the buyer's journey
spec describes instant post-purchase access with no signup step.
"""
from __future__ import annotations
import os

from flask import Flask, render_template, request

from app.data import get_account_by_token, get_completed_sops, get_workflowiq_runs

app = Flask(__name__)

CALL_IN_NUMBER = os.getenv("SOPBOT_CALL_NUMBER", "+1 903-626-7053")
WORKFLOWIQ_URL = os.getenv("WORKFLOWIQ_URL", "#")


@app.route("/health")
def health():
    return {"status": "ok"}


@app.route("/")
def dashboard():
    token = request.args.get("token", "")

    if not token:
        return render_template("token_prompt.html")

    account = get_account_by_token(token)
    if account is None:
        return render_template("invalid_token.html"), 404

    sops = sorted(get_completed_sops(account), key=lambda s: s.call_timestamp, reverse=True)
    runs = sorted(get_workflowiq_runs(account), key=lambda r: r.run_timestamp, reverse=True)
    progress_pct = int(
        min(account.sop_credits_used / account.sop_pack_size, 1.0) * 100
        if account.sop_pack_size
        else 0
    )

    return render_template(
        "dashboard.html",
        account=account,
        sops=sops,
        runs=runs,
        progress_pct=progress_pct,
        call_in_number=CALL_IN_NUMBER,
        workflowiq_url=WORKFLOWIQ_URL,
        show_upsell=len(sops) >= 2,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
