"""Background job runner for long-running Claude analysis.

Runs run_analysis()/build_pdf() on a daemon thread instead of blocking the
Streamlit script run. Streamlit's single WebSocket connection has proven
unreliable held open across the full 1-3 minute analysis (repeated silent
disconnects observed in production, root cause undetermined — see
workflowiq/README.md). Running the work in a background thread and polling
its status via short reruns avoids depending on one long-lived connection.
"""
from __future__ import annotations
import threading
import traceback
from dataclasses import dataclass, field
from typing import Optional

from app.schemas import SopInput, RunResult


@dataclass
class JobState:
    status: str = "running"  # running | complete | error
    result: Optional[RunResult] = None
    pdf_path: Optional[str] = None
    error: Optional[str] = None
    sops: list = field(default_factory=list)
    order: Optional[object] = None  # PendingOrder this run fulfils, if any (see app.order_delivery)


def start_job(sops: list[SopInput]) -> JobState:
    """Launch the analysis + PDF build on a background thread. Returns a
    JobState the caller should stash in st.session_state and poll."""
    from app.claude_engine.engine import run_analysis
    from app.pdf_generator.builder import build_pdf

    state = JobState(sops=sops)

    def _worker():
        try:
            result: RunResult = run_analysis(sops)
            pdf_path = build_pdf(result)
            state.result = result
            state.pdf_path = pdf_path
            state.status = "complete"
        except Exception as e:
            state.error = f"{e}\n\n{traceback.format_exc()}"
            state.status = "error"

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return state
