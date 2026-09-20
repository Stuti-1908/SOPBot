"""WorkflowIQ main UI — SOP input, run trigger, results display."""
import os
import streamlit as st

from app.google_drive.reader import fetch_sop_from_drive
from app.job_runner import start_job
from app.airtable_logger.logger import log_run
from app.order_delivery import list_pending_orders, mark_order_complete, email_report_to_customer
from app.schemas import SopInput


def render_ui() -> None:
    st.title("WorkflowIQ ⚙️")
    st.caption("Process optimization reports powered by DadaAI")

    st.divider()

    # A job is in flight or finished — poll/display it instead of showing the form again.
    if "job" in st.session_state:
        _poll_and_display()
        return

    _render_pending_orders()

    mode = st.radio(
        "SOP Source",
        ["Google Drive URL", "Paste text"],
        horizontal=True,
    )

    sops: list[SopInput] = []

    if mode == "Google Drive URL":
        urls_raw = st.text_area(
            "Google Doc URLs (one per line, max 8)",
            height=150,
            placeholder="https://docs.google.com/document/d/...",
        )
        client_name = st.text_input("Client name")
        if st.button("Fetch & Analyse", type="primary"):
            urls = [u.strip() for u in urls_raw.splitlines() if u.strip()]
            if not urls:
                st.error("Paste at least one Google Doc URL.")
                return
            if len(urls) > int(os.getenv("MAX_SOPS_PER_RUN", 8)):
                st.error(f"Maximum {os.getenv('MAX_SOPS_PER_RUN', 8)} SOPs per run.")
                return
            with st.spinner("Fetching SOPs from Drive…"):
                for url in urls:
                    try:
                        text = fetch_sop_from_drive(url)
                        sops.append(SopInput(source_url=url, text=text, client_name=client_name))
                    except Exception as e:
                        st.error(f"Failed to fetch {url}: {e}")
                        return
            _launch(sops)

    else:
        sop_text = st.text_area("Paste SOP text", height=300)
        client_name = st.text_input("Client name")
        process_name = st.text_input("Process name")
        if st.button("Analyse", type="primary"):
            if not sop_text.strip():
                st.error("Paste SOP text first.")
                return
            word_count = len(sop_text.split())
            min_w = int(os.getenv("MIN_SOP_WORDS", 100))
            max_w = int(os.getenv("MAX_SOP_WORDS", 15000))
            if word_count < min_w:
                st.error(f"SOP too short ({word_count} words, minimum {min_w}).")
                return
            if word_count > max_w:
                st.error(f"SOP too long ({word_count} words, maximum {max_w}).")
                return
            sops.append(SopInput(text=sop_text, client_name=client_name, process_name=process_name))
            _launch(sops)


def _deliver_to_order(job, pdf_path: str, result) -> None:
    """Marks the linked Supabase order Complete and emails the customer
    their PDF, closing the purchase -> report loop. Runs once per order
    (guarded by a session_state flag) since Streamlit reruns this whole
    function on every interaction while the completed state is displayed."""
    opp_count = sum(len(sr.automation_map.opportunities) for sr in result.sop_results)
    processes = ", ".join(s.process_name for s in job.sops if s.process_name)

    try:
        mark_order_complete(
            order_id=job.order.id,
            process_names=processes,
            sops_analysed=len(job.sops),
            automation_opportunities_found=opp_count,
            pdf_filename=os.path.basename(pdf_path),
        )
        email_report_to_customer(job.order.contact_email, pdf_path)
        st.success(f"Order marked complete and report emailed to {job.order.contact_email}.")
    except Exception as e:
        st.error(f"Report generated, but delivery to the customer failed: {e}. Download the PDF below and send it manually.")
    finally:
        st.session_state[f"delivered_{job.order.id}"] = True


def _render_pending_orders() -> None:
    """Shows WorkflowIQ orders paid for but not yet run (see
    payments/app/fulfillment.py::_write_workflowiq_run), so the operator
    knows what's owed and can tie a run to the right customer for delivery."""
    try:
        orders = list_pending_orders()
    except Exception as e:
        st.warning(f"Couldn't load pending orders: {e}")
        return

    if not orders:
        st.caption("No pending WorkflowIQ orders.")
        return

    st.subheader(f"Pending orders ({len(orders)})")
    labels = ["— run without linking to an order —"] + [
        f"{o.contact_email} · {o.report_type} · {o.payment_id}" for o in orders
    ]
    choice = st.selectbox("Run this analysis for:", labels, key="pending_order_choice")
    if choice != labels[0]:
        st.session_state["selected_order"] = orders[labels.index(choice) - 1]
    else:
        st.session_state.pop("selected_order", None)

    st.divider()


def _launch(sops: list[SopInput]) -> None:
    """Kick off the analysis on a background thread and switch into polling mode."""
    st.session_state["job"] = start_job(sops)
    st.session_state["job"].order = st.session_state.get("selected_order")
    st.rerun()


@st.fragment(run_every=2)
def _poll_running_job() -> None:
    """Runs on its own 2s timer via Streamlit's native fragment auto-refresh,
    isolated from the rest of the page. This replaced a manual time.sleep() +
    st.rerun() loop that occasionally threw 'Bad message format: Tried to use
    SessionInfo before it was initialized' — a known issue when a full-page
    rerun is triggered again before the previous one's session handshake has
    settled. st.fragment(run_every=...) is Streamlit's purpose-built API for
    exactly this polling pattern and only reruns the fragment, not the page."""
    job = st.session_state["job"]
    if job.status != "running":
        st.rerun()
        return
    st.info("Running AI analysis (this takes 1–3 minutes)… this page refreshes itself, no need to reload.")
    st.progress(50, text="Analysing with Claude…")
    if st.button("Cancel"):
        del st.session_state["job"]
        st.rerun()


def _poll_and_display() -> None:
    """Called on every rerun while a job is in flight. Each call is a short,
    independent script run — no single request/connection stays open for the
    full analysis duration, unlike the previous blocking implementation."""
    job = st.session_state["job"]

    if job.status == "running":
        _poll_running_job()
        return

    if job.status == "error":
        st.error(f"Analysis failed: {job.error}")
        log_run(job.sops, status="Error", error=job.error)
        if st.button("Start over"):
            del st.session_state["job"]
            st.rerun()
        return

    # complete
    result = job.result
    pdf_path = job.pdf_path
    log_run(job.sops, status="Complete", result=result, pdf_path=pdf_path)

    st.success("Analysis complete!")

    if job.order and not st.session_state.get(f"delivered_{job.order.id}"):
        _deliver_to_order(job, pdf_path, result)

    with open(pdf_path, "rb") as f:
        st.download_button(
            label="Download Report PDF",
            data=f,
            file_name=os.path.basename(pdf_path),
            mime="application/pdf",
        )

    if st.button("Run another analysis"):
        del st.session_state["job"]
        st.rerun()

    st.divider()
    st.subheader("Executive Summary")
    st.markdown(result.executive_summary)

    if result.cross_process:
        st.subheader("Cross-Process Insights")
        st.markdown(result.cross_process.insights)
