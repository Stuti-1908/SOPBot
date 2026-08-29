"""Data access for the owner dashboard: real Airtable reads, with a mock
provider so the dashboard is testable while Airtable's API is unavailable
(PUBLIC_API_BILLING_LIMIT_EXCEEDED as of 2026-08 - see project notes).

Set DASHBOARD_DATA_SOURCE=mock (default) to use realistic sample data, or
DASHBOARD_DATA_SOURCE=airtable to hit the real base once it's unblocked.
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


# ── Real Airtable provider ──────────────────────────────────────────────────

def _airtable_table(table_name: str):
    from pyairtable import Api
    token = os.environ["AIRTABLE_API_TOKEN"]
    base_id = os.environ["AIRTABLE_BASE_ID"]
    return Api(token).table(base_id, table_name)


def _get_airtable_account(token: str) -> Optional[Account]:
    clients_table = os.getenv("AIRTABLE_CLIENTS_TABLE", "Clients")
    table = _airtable_table(clients_table)
    matches = table.all(formula=f"{{Dashboard Token}} = '{token}'")
    if not matches:
        return None
    f = matches[0]["fields"]
    return Account(
        record_id=matches[0]["id"],
        client_name=f.get("Client Name", ""),
        dashboard_token=f.get("Dashboard Token", ""),
        call_pin=f.get("Call PIN", ""),
        sop_pack_size=int(f.get("SOP Pack Size", 0) or 0),
        sop_credits_used=int(f.get("SOP Credits Used", 0) or 0),
        contact_email=f.get("Contact Email", ""),
        status=f.get("Status", "Active"),
    )


def _get_airtable_sops(account_id: str) -> list[CompletedSop]:
    calls_table = os.getenv("AIRTABLE_CALLS_TABLE", "Calls Log")
    table = _airtable_table(calls_table)
    records = table.all(formula=f"AND({{Client}} = '{account_id}', {{Status}} = 'Complete')")
    return [
        CompletedSop(
            call_id=r["fields"].get("Call ID", r["id"]),
            process_name=r["fields"].get("Process Name", ""),
            employee_name=r["fields"].get("Employee Name", ""),
            call_timestamp=datetime.fromisoformat(r["fields"]["Call Timestamp"]) if r["fields"].get("Call Timestamp") else _now,
            sop_doc_url=r["fields"].get("SOP Doc URL", ""),
            status=r["fields"].get("Status", "Complete"),
        )
        for r in records
    ]


def _get_airtable_runs(account_id: str) -> list[WorkflowIqRun]:
    runs_table = os.getenv("AIRTABLE_RUNS_TABLE", "WorkflowIQ Runs")
    table = _airtable_table(runs_table)
    records = table.all(formula=f"{{Client}} = '{account_id}'")
    return [
        WorkflowIqRun(
            run_timestamp=datetime.fromisoformat(r["fields"]["Run Timestamp"]) if r["fields"].get("Run Timestamp") else _now,
            process_names=r["fields"].get("Process Names", ""),
            sops_analysed=int(r["fields"].get("SOPs Analysed", 0) or 0),
            automation_opportunities_found=int(r["fields"].get("Automation Opportunities Found", 0) or 0),
            pdf_filename=r["fields"].get("PDF Filename", ""),
            report_type=r["fields"].get("Report Type", "Single-SOP"),
        )
        for r in records
    ]


# ── Public interface (routes to mock or real based on DATA_SOURCE) ─────────

def get_account_by_token(token: str) -> Optional[Account]:
    if DATA_SOURCE == "airtable":
        return _get_airtable_account(token)
    return _get_mock_account(token)


def get_completed_sops(account: Account) -> list[CompletedSop]:
    if DATA_SOURCE == "airtable":
        return _get_airtable_sops(account.record_id)
    return _get_mock_sops(account.record_id)


def get_workflowiq_runs(account: Account) -> list[WorkflowIqRun]:
    if DATA_SOURCE == "airtable":
        return _get_airtable_runs(account.record_id)
    return _get_mock_runs(account.record_id)
