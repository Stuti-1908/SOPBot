"""WorkflowIQ main UI - SOP input, run trigger, results display."""
import os
import streamlit as st

from app.google_drive.reader import fetch_sop_from_drive, find_customer_sop_docs
from app.job_runner import start_job
from app.airtable_logger.logger import log_run
from app.order_delivery import list_pending_orders, mark_order_complete, email_report_to_customer
from app.schemas import SopInput
from app.theme import badge


def render_ui() -> None:
    # A job is in flight or finished - poll/display it instead of showing the form again.
    if "job" in st.session_state:
        _poll_and_display()
        return

    st.markdown("#### 1. Who is this report for?")
    _render_pending_orders()

    st.markdown("#### 2. Add the SOP(s) to analyse")
    _render_sop_input()


def _render_sop_input() -> None:
    with st.container(border=True):
        mode = st.radio(
            "SOP source",
            ["Google Drive link", "Paste text"],
            horizontal=True,
            label_visibility="collapsed",
        )

        sops: list[SopInput] = []

        if mode == "Google Drive link":
            max_sops = int(os.getenv("MAX_SOPS_PER_RUN", 30))
            urls_raw = st.text_area(
                f"Google Doc links (one per line, up to {max_sops})",
                height=130,
                value=st.session_state.pop("url_prefill", ""),
                placeholder="https://docs.google.com/document/d/...",
            )
            client_name = st.text_input("Client name")
            if st.button("Fetch and analyse", type="primary", use_container_width=True):
                urls = [u.strip() for u in urls_raw.splitlines() if u.strip()]
                if not urls:
                    st.error("Add at least one Google Doc link.")
                    return
                if len(urls) > max_sops:
                    st.error(f"That's {len(urls)} links - the limit for this run is {max_sops}.")
                    return
                with st.spinner("Fetching SOPs from Drive..."):
                    for url in urls:
                        try:
                            text = fetch_sop_from_drive(url)
                            sops.append(SopInput(source_url=url, text=text, client_name=client_name))
                        except Exception as e:
                            st.error(f"Couldn't open {url}: {e}")
                            return
                _launch(sops)

        else:
            sop_text = st.text_area("Paste the SOP text", height=260)
            client_name = st.text_input("Client name")
            process_name = st.text_input("Process name")
            if st.button("Analyse", type="primary", use_container_width=True):
                if not sop_text.strip():
                    st.error("Paste the SOP text first.")
                    return
                word_count = len(sop_text.split())
                min_w = int(os.getenv("MIN_SOP_WORDS", 100))
                max_w = int(os.getenv("MAX_SOP_WORDS", 15000))
                if word_count < min_w:
                    st.error(f"This is {word_count} words - needs at least {min_w} to analyse well.")
                    return
                if word_count > max_w:
                    st.error(f"This is {word_count} words - the limit per SOP is {max_w}.")
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
        st.success(f"Order marked complete and the report was emailed to {job.order.contact_email}.")
    except Exception as e:
        st.error(f"Report generated, but sending it to the customer failed: {e}. Download it below and send it yourself.")
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

    with st.container(border=True):
        if not orders:
            st.caption("No paid orders waiting - pick this if you're running a one-off analysis instead.")
        else:
            st.markdown(
                f"{badge(f'{len(orders)} waiting', 'pending')}",
                unsafe_allow_html=True,
            )

        labels = ["Just running an analysis, not tied to an order"] + [
            f"{o.contact_email}  -  {o.report_type}" for o in orders
        ]
        choice = st.selectbox("Order", labels, key="pending_order_choice", label_visibility="collapsed")
        if choice != labels[0]:
            st.session_state["selected_order"] = orders[labels.index(choice) - 1]
        else:
            st.session_state.pop("selected_order", None)

        _render_found_sops_for_selected_order()


def _render_found_sops_for_selected_order() -> None:
    """When an order is selected, look up that customer's company Drive
    folder and list every SOP found there as checkboxes - saves the operator
    from manually hunting for and pasting Drive links (previously the one
    fully-manual step in the purchase -> report -> delivery pipeline).
    Falls back silently to the existing manual URL paste box if no company
    match or no folder is found - this is a convenience, not a requirement."""
    order = st.session_state.get("selected_order")
    if not order:
        return

    if not order.client_name:
        st.caption("No account on file for this email yet - add the SOP link(s) below.")
        return

    docs = st.session_state.get(f"found_sops_{order.id}")
    if docs is None:
        with st.spinner(f"Looking for {order.client_name}'s SOPs in Drive..."):
            try:
                docs = find_customer_sop_docs(order.client_name)
            except Exception as e:
                st.warning(f"Couldn't search Drive for this customer's SOPs: {e}")
                docs = []
        st.session_state[f"found_sops_{order.id}"] = docs

    if not docs:
        st.caption(f"No SOP folder found for {order.client_name} - add the link(s) below.")
        return

    st.markdown(f"Found **{len(docs)} SOP(s)** for {order.client_name} - pick which to include:")
    selected_urls = []
    for i, doc in enumerate(docs):
        checked = st.checkbox(doc["name"], key=f"sop_check_{order.id}_{i}")
        if checked:
            selected_urls.append(doc["url"])
    st.session_state[f"selected_sop_urls_{order.id}"] = selected_urls
    if selected_urls:
        if st.button(f"Use {len(selected_urls)} selected"):
            st.session_state["url_prefill"] = "\n".join(selected_urls)
            st.rerun()


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
    SessionInfo before it was initialized' - a known issue when a full-page
    rerun is triggered again before the previous one's session handshake has
    settled. st.fragment(run_every=...) is Streamlit's purpose-built API for
    exactly this polling pattern and only reruns the fragment, not the page."""
    job = st.session_state["job"]
    if job.status != "running":
        st.rerun()
        return
    st.markdown(badge("Running", "running"), unsafe_allow_html=True)
    st.caption("Usually takes 1-3 minutes. This page updates itself - no need to reload.")
    st.progress(50)
    if st.button("Cancel"):
        del st.session_state["job"]
        st.rerun()


def _poll_and_display() -> None:
    """Called on every rerun while a job is in flight. Each call is a short,
    independent script run - no single request/connection stays open for the
    full analysis duration, unlike the previous blocking implementation."""
    job = st.session_state["job"]

    if job.status == "running":
        _poll_running_job()
        return

    if job.status == "error":
        st.markdown(badge("Failed", "error"), unsafe_allow_html=True)
        st.error(job.error)
        log_run(job.sops, status="Error", error=job.error)
        if st.button("Start over"):
            del st.session_state["job"]
            st.rerun()
        return

    # complete
    result = job.result
    pdf_path = job.pdf_path
    log_run(job.sops, status="Complete", result=result, pdf_path=pdf_path)

    st.markdown(badge("Complete", "complete"), unsafe_allow_html=True)

    if job.order and not st.session_state.get(f"delivered_{job.order.id}"):
        _deliver_to_order(job, pdf_path, result)

    with open(pdf_path, "rb") as f:
        st.download_button(
            label="Download report PDF",
            data=f,
            file_name=os.path.basename(pdf_path),
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )

    if st.button("Run another analysis", use_container_width=True):
        del st.session_state["job"]
        st.rerun()

    st.divider()
    st.markdown("#### Executive summary")
    st.markdown(result.executive_summary)

    if result.cross_process:
        st.markdown("#### Cross-process insights")
        st.markdown(result.cross_process.insights)
