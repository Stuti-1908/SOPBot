"""Data access for the owner dashboard: real Supabase reads, with a mock
provider so the dashboard is testable without a live database.

Set DASHBOARD_DATA_SOURCE=mock (default) to use realistic sample data, or
DASHBOARD_DATA_SOURCE=supabase to hit the real project once SUPABASE_URL /
SUPABASE_SERVICE_KEY are configured.
"""
from __future__ import annotations
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.schemas import Account, CompletedSop, WorkflowIqRun

DATA_SOURCE = os.getenv("DASHBOARD_DATA_SOURCE", "mock")


# ── Mock provider ───────────────────────────────────────────────────────────

_MOCK_ACCOUNT = Account(
    record_id="rec_mock001",
    client_name="Relentless Marketing",
    dashboard_token="demo-token-relentless",
    call_pin="4821",
    sop_pack_size=15,
    sop_credits_used=3,
    contact_email="owner@relentlessmarketing.example",
)

_now = datetime.now(timezone.utc)
_MOCK_SOPS = [
    CompletedSop(
        call_id="call_001",
        process_name="Customer Refund Processing",
        employee_name="Jordan",
        call_timestamp=_now - timedelta(days=6),
        sop_doc_url="https://docs.google.com/document/d/example1",
    ),
    CompletedSop(
        call_id="call_002",
        process_name="New Client Onboarding",
        employee_name="Priya",
        call_timestamp=_now - timedelta(days=3),
        sop_doc_url="https://docs.google.com/document/d/example2",
    ),
    CompletedSop(
        call_id="call_003",
        process_name="Weekly Ad Spend Reporting",
        employee_name="Marcus",
        call_timestamp=_now - timedelta(hours=14),
        sop_doc_url="https://docs.google.com/document/d/example3",
    ),
]

_MOCK_RUNS = [
    WorkflowIqRun(
        run_timestamp=_now - timedelta(days=2),
        process_names="Customer Refund Processing",
        sops_analysed=1,
        automation_opportunities_found=5,
        pdf_filename="Relentless_Marketing_WorkflowIQ_20260827.pdf",
        report_type="Single-SOP",
    ),
]


def _get_mock_account(token: str) -> Optional[Account]:
    if token == _MOCK_ACCOUNT.dashboard_token:
        return _MOCK_ACCOUNT
    return None


def _get_mock_sops(account_id: str) -> list[CompletedSop]:
    return _MOCK_SOPS


def _get_mock_runs(account_id: str) -> list[WorkflowIqRun]:
    return _MOCK_RUNS


# ── Real Supabase provider ──────────────────────────────────────────────────

def _supabase_client():
    from supabase import create_client
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    return create_client(url, key)


def _get_supabase_account(token: str) -> Optional[Account]:
    client = _supabase_client()
    res = client.table("clients").select("*").eq("dashboard_token", token).limit(1).execute()
    if not res.data:
        return None
    r = res.data[0]
    return Account(
        record_id=r["id"],
        client_name=r.get("client_name", ""),
        dashboard_token=r.get("dashboard_token", ""),
        call_pin=r.get("call_pin", ""),
        sop_pack_size=int(r.get("sop_pack_size", 0) or 0),
        sop_credits_used=int(r.get("sop_credits_used", 0) or 0),
        contact_email=r.get("contact_email", ""),
        status=r.get("status", "Active"),
    )


def _get_supabase_sops(account_id: str) -> list[CompletedSop]:
    client = _supabase_client()
    res = (
        client.table("calls_log")
        .select("*")
        .eq("client_id", account_id)
        .eq("status", "Complete")
        .execute()
    )
    return [
        CompletedSop(
            call_id=r.get("call_id", r["id"]),
            process_name=r.get("process_name", ""),
            employee_name=r.get("employee_name", ""),
            call_timestamp=datetime.fromisoformat(r["call_timestamp"]) if r.get("call_timestamp") else _now,
            sop_doc_url=r.get("sop_doc_url", ""),
            status=r.get("status", "Complete"),
        )
        for r in res.data
    ]


def _get_supabase_runs(account_id: str) -> list[WorkflowIqRun]:
    client = _supabase_client()
    res = client.table("workflowiq_runs").select("*").eq("client_id", account_id).execute()
    return [
        WorkflowIqRun(
            run_timestamp=datetime.fromisoformat(r["run_timestamp"]) if r.get("run_timestamp") else _now,
            process_names=r.get("process_names", ""),
            sops_analysed=int(r.get("sops_analysed", 0) or 0),
            automation_opportunities_found=int(r.get("automation_opportunities_found", 0) or 0),
            pdf_filename=r.get("pdf_filename", ""),
            report_type=r.get("report_type", "Single-SOP"),
        )
        for r in res.data
    ]


# ── Public interface (routes to mock or real based on DATA_SOURCE) ─────────

def get_account_by_token(token: str) -> Optional[Account]:
    if DATA_SOURCE == "supabase":
        return _get_supabase_account(token)
    return _get_mock_account(token)


def get_completed_sops(account: Account) -> list[CompletedSop]:
    if DATA_SOURCE == "supabase":
        return _get_supabase_sops(account.record_id)
    return _get_mock_sops(account.record_id)


def get_workflowiq_runs(account: Account) -> list[WorkflowIqRun]:
    if DATA_SOURCE == "supabase":
        return _get_supabase_runs(account.record_id)
    return _get_mock_runs(account.record_id)
