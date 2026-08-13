"""WorkflowIQ main UI — SOP input, run trigger, results display."""
import os
import streamlit as st

from app.google_drive.reader import fetch_sop_from_drive
from app.job_runner import start_job
from app.airtable_logger.logger import log_run
from app.schemas import SopInput


def render_ui() -> None:
    st.title("WorkflowIQ ⚙️")
    st.caption("Process optimization reports powered by DadaAI")

    st.divider()

    # A job is in flight or finished — poll/display it instead of showing the form again.
    if "job" in st.session_state:
        _poll_and_display()
        return

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


def _launch(sops: list[SopInput]) -> None:
    """Kick off the analysis on a background thread and switch into polling mode."""
    st.session_state["job"] = start_job(sops)
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
