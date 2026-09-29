"""Background job runner for long-running Claude analysis.

Runs run_analysis()/build_pdf() on a daemon thread instead of blocking the
Streamlit script run. Streamlit's single WebSocket connection has proven
unreliable held open across the full 1-3 minute analysis (repeated silent
disconnects observed in production, root cause undetermined - see
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
    label: str = ""  # display name for this job when run as part of a batch (e.g. client name)


def _run_worker(state: JobState, sops: list[SopInput]) -> None:
    from app.claude_engine.engine import run_analysis
    from app.pdf_generator.builder import build_pdf

    try:
        result: RunResult = run_analysis(sops)
        pdf_path = build_pdf(result)
        state.result = result
        state.pdf_path = pdf_path
        state.status = "complete"
    except Exception as e:
        state.error = f"{e}\n\n{traceback.format_exc()}"
        state.status = "error"


def start_job(sops: list[SopInput]) -> JobState:
    """Launch a single analysis + PDF build on a background thread. Returns
    a JobState the caller should stash in st.session_state and poll."""
    state = JobState(sops=sops)
    thread = threading.Thread(target=_run_worker, args=(state, sops), daemon=True)
    thread.start()
    return state


def start_batch(runs: list[tuple[list[SopInput], str, object]]) -> list[JobState]:
    """Launch several independent analyses concurrently, each on its own
    thread. `runs` is a list of (sops, label, order) tuples - label is a
    display name (e.g. a client name) shown while the batch is in flight,
    order is the PendingOrder this run fulfils, or None for a standalone run.

    Each job is fully independent (own SopInput list, own PDF, own possible
    order to mark complete) - this is what makes both "multiple clients in
    one Drive-link submission" and "run several queued orders at once"
    possible without them interfering with each other."""
    states = []
    for sops, label, order in runs:
        state = JobState(sops=sops, label=label, order=order)
        thread = threading.Thread(target=_run_worker, args=(state, sops), daemon=True)
        thread.start()
        states.append(state)
    return states
