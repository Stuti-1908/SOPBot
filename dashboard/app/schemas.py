"""Data shapes for the owner dashboard. Mirrors the multi-tenant Airtable
schema plan (docs/runbooks - Airtable schema evolution notes) so mock data
and real Airtable reads produce the same shape for the UI to render."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Account:
    record_id: str
    client_name: str
    dashboard_token: str
    call_pin: str
    sop_pack_size: int
    sop_credits_used: int
    contact_email: str = ""
    status: str = "Active"

    @property
    def sop_credits_remaining(self) -> int:
        return max(self.sop_pack_size - self.sop_credits_used, 0)


@dataclass
class CompletedSop:
    call_id: str
    process_name: str
    employee_name: str
    call_timestamp: datetime
    sop_doc_url: str
    status: str = "Complete"


@dataclass
class WorkflowIqRun:
    run_timestamp: datetime
    process_names: str
    sops_analysed: int
    automation_opportunities_found: int
    pdf_filename: str
    report_type: str = "Single-SOP"
