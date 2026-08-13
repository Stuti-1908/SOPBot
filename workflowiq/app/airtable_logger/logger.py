"""Log WorkflowIQ runs to Airtable — WorkflowIQ Runs table."""
from __future__ import annotations
import os
from datetime import datetime, timezone
from typing import Optional

from pyairtable import Api

from app.schemas import SopInput, RunResult


def _table():
    token = os.environ["AIRTABLE_API_TOKEN"]
    base_id = os.environ["AIRTABLE_BASE_ID"]
    table_name = os.getenv("AIRTABLE_RUNS_TABLE", "WorkflowIQ Runs")
    return Api(token).table(base_id, table_name)


def log_run(
    sops: list[SopInput],
    status: str,
    result: Optional[RunResult] = None,
    pdf_path: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """Create a record in WorkflowIQ Runs; silently swallow errors to never block the UI."""
    try:
        client = sops[0].client_name if sops else ""
        processes = ", ".join(s.process_name for s in sops if s.process_name)
        opp_count = 0
        if result:
            for sr in result.sop_results:
                opp_count += len(sr.automation_map.opportunities)

        record = {
            "Run Timestamp": datetime.now(timezone.utc).isoformat(),
            "Client Name": client,
            "SOPs Analysed": len(sops),
            "Process Names": processes,
            "Status": status,
            "Automation Opportunities Found": opp_count,
            "PDF Filename": os.path.basename(pdf_path) if pdf_path else "",
            "Error Detail": error or "",
        }
        _table().create(record)
    except Exception as exc:
        # Log to stderr but never crash the UI
        import sys
        print(f"[airtable_logger] WARNING: failed to log run: {exc}", file=sys.stderr)
