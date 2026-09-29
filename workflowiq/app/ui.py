"""WorkflowIQ main UI - SOP input, run trigger, results display."""
import os
import streamlit as st

from app.google_drive.reader import fetch_sop_from_drive, find_customer_sop_docs
from app.job_runner import start_job, start_batch
from app.airtable_logger.logger import log_run
from app.order_delivery import list_pending_orders, mark_order_complete, email_report_to_customer
from app.schemas import SopInput
from app.theme import badge


def render_ui() -> None:
    # A batch is in flight or finished - poll/display it instead of showing the form again.
    if "jobs" in st.session_state:
        _poll_and_display_batch()
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

        if mode == "Google Drive link":
            _render_drive_input()
        else:
            _render_paste_text_input()


def _render_drive_input() -> None:
    max_sops = int(os.getenv("MAX_SOPS_PER_RUN", 30))

    client_mode = st.radio(
        "How many clients are in this batch?",
        ["Single client", "Multiple clients"],
        horizontal=True,
        key="drive_client_mode",
    )

    if client_mode == "Single client":
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
            sops = _fetch_sops(urls, client_name)
            if sops is None:
                return
            _launch_batch([(sops, client_name or "Client", st.session_state.get("selected_order"))])

    else:
        st.caption("Add one row per Drive link. Rows with the same client name are combined into one report for that client - different names produce separate reports.")
        default_rows = [{"Google Doc link": "", "Client name": ""} for _ in range(3)]
        rows = st.data_editor(
            st.session_state.get("multi_client_rows", default_rows),
            num_rows="dynamic",
            use_container_width=True,
            key="multi_client_editor",
            column_config={
                "Google Doc link": st.column_config.TextColumn(width="large"),
                "Client name": st.column_config.TextColumn(width="medium"),
            },
        )
        st.session_state["multi_client_rows"] = rows

        if st.button("Fetch and analyse all", type="primary", use_container_width=True):
            filled = [r for r in rows if (r.get("Google Doc link") or "").strip()]
            if not filled:
                st.error("Add at least one Google Doc link.")
                return
            missing_client = [r for r in filled if not (r.get("Client name") or "").strip()]
            if missing_client:
                st.error("Every link needs a client name so reports can be told apart.")
                return
            if len(filled) > max_sops:
                st.error(f"That's {len(filled)} links total - the limit for this run is {max_sops}.")
                return

            groups: dict[str, list[str]] = {}
            for r in filled:
                name = r["Client name"].strip()
                groups.setdefault(name, []).append(r["Google Doc link"].strip())

            runs = []
            for client_name, urls in groups.items():
                sops = _fetch_sops(urls, client_name)
                if sops is None:
                    return
                runs.append((sops, client_name, None))

            _launch_batch(runs)


def _fetch_sops(urls: list[str], client_name: str) -> list[SopInput] | None:
    """Fetches each Drive URL's text; returns None (after showing an error)
    on the first failure so the caller can bail out cleanly."""
    sops: list[SopInput] = []
    with st.spinner(f"Fetching SOPs for {client_name or 'this client'}..."):
        for url in urls:
            try:
                text = fetch_sop_from_drive(url)
                sops.append(SopInput(source_url=url, text=text, client_name=client_name))
            except Exception as e:
                st.error(f"Couldn't open {url}: {e}")
                return None
    return sops


def _render_paste_text_input() -> None:
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
        sops = [SopInput(text=sop_text, client_name=client_name, process_name=process_name)]
        _launch_batch([(sops, client_name or "Client", st.session_state.get("selected_order"))])


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
    payments/app/fulfillment.py::_write_workflowiq_run). Lets the operator
    either pick one order for a single manual run (the existing flow, still
    used when an order's SOPs need to be pasted in manually), or check
    several orders and run them all at once - each checked order is only
    included in the batch if find_customer_sop_docs() can actually match its
    company to a Drive folder, since there is no per-order manual SOP entry
    step in the batch path."""
    try:
        orders = list_pending_orders()
    except Exception as e:
        st.warning(f"Couldn't load pending orders: {e}")
        return

    with st.container(border=True):
        if not orders:
            st.caption("No paid orders waiting - pick this if you're running a one-off analysis instead.")
            st.session_state.pop("selected_order", None)
            return

        st.markdown(f"{badge(f'{len(orders)} waiting', 'pending')}", unsafe_allow_html=True)

        batch_mode = st.checkbox("Select multiple orders to run as a batch", key="orders_batch_mode")

        if batch_mode:
            _render_batch_order_picker(orders)
        else:
            labels = ["Just running an analysis, not tied to an order"] + [
                f"{o.contact_email}  -  {o.report_type}" for o in orders
            ]
            choice = st.selectbox("Order", labels, key="pending_order_choice", label_visibility="collapsed")
            if choice != labels[0]:
                st.session_state["selected_order"] = orders[labels.index(choice) - 1]
            else:
                st.session_state.pop("selected_order", None)

            _render_found_sops_for_selected_order()


def _render_batch_order_picker(orders: list) -> None:
    checked_orders = []
    for o in orders:
        checked = st.checkbox(
            f"{o.contact_email}  -  {o.report_type}",
            key=f"batch_check_{o.id}",
        )
        if checked:
            checked_orders.append(o)

    if not checked_orders:
        st.caption("Check the orders you want to run together.")
        return

    st.caption(f"{len(checked_orders)} selected. Each one runs using whatever SOPs are auto-found for that client - orders with no Drive match are skipped.")
    if st.button(f"Run {len(checked_orders)} selected", type="primary", use_container_width=True):
        runs = []
        skipped = []
        with st.spinner("Looking up each client's SOPs in Drive..."):
            for o in checked_orders:
                if not o.client_name:
                    skipped.append((o, "no account on file for this email"))
                    continue
                try:
                    docs = find_customer_sop_docs(o.client_name)
                except Exception as e:
                    skipped.append((o, f"Drive lookup failed: {e}"))
                    continue
                if not docs:
                    skipped.append((o, f"no SOP folder found for {o.client_name}"))
                    continue
                sops = []
                fetch_failed = False
                for doc in docs:
                    try:
                        text = fetch_sop_from_drive(doc["url"])
                        sops.append(SopInput(source_url=doc["url"], text=text, client_name=o.client_name))
                    except Exception as e:
                        skipped.append((o, f"couldn't open {doc['name']}: {e}"))
                        fetch_failed = True
                        break
                if fetch_failed or not sops:
                    continue
                runs.append((sops, o.client_name, o))

        if skipped:
            for o, reason in skipped:
                st.warning(f"Skipped {o.contact_email}: {reason}")

        if not runs:
            st.error("None of the selected orders could be auto-run - handle them individually instead.")
            return

        _launch_batch(runs)


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


def _launch_batch(runs: list[tuple[list[SopInput], str, object]]) -> None:
    """Kick off one or more independent analyses and switch into batch
    polling mode. `runs` is (sops, label, order) tuples - see
    job_runner.start_batch."""
    st.session_state["jobs"] = start_batch(runs)
    st.session_state.pop("multi_client_rows", None)
    st.rerun()


@st.fragment(run_every=2)
def _poll_running_jobs() -> None:
    """Runs on its own 2s timer via Streamlit's native fragment auto-refresh,
    isolated from the rest of the page. This replaced a manual time.sleep() +
    st.rerun() loop that occasionally threw 'Bad message format: Tried to use
    SessionInfo before it was initialized' - a known issue when a full-page
    rerun is triggered again before the previous one's session handshake has
    settled. st.fragment(run_every=...) is Streamlit's purpose-built API for
    exactly this polling pattern and only reruns the fragment, not the page."""
    jobs = st.session_state["jobs"]
    still_running = [j for j in jobs if j.status == "running"]

    if not still_running:
        st.rerun()
        return

    st.markdown(badge(f"Running {len(still_running)} of {len(jobs)}", "running"), unsafe_allow_html=True)
    st.caption("Usually takes 1-3 minutes per client. This page updates itself - no need to reload.")
    for job in jobs:
        name = job.label or "Analysis"
        if job.status == "running":
            st.progress(50, text=f"{name}: analysing with Claude...")
        elif job.status == "complete":
            st.progress(100, text=f"{name}: done")
        else:
            st.progress(100, text=f"{name}: failed")

    if st.button("Cancel remaining"):
        del st.session_state["jobs"]
        st.rerun()


def _poll_and_display_batch() -> None:
    """Called on every rerun while a batch is in flight. Each call is a
    short, independent script run - no single request/connection stays open
    for the full analysis duration."""
    jobs = st.session_state["jobs"]

    if any(j.status == "running" for j in jobs):
        _poll_running_jobs()
        return

    st.markdown(badge(f"{len(jobs)} report(s) finished", "complete"), unsafe_allow_html=True)

    for i, job in enumerate(jobs):
        name = job.label or f"Report {i + 1}"
        with st.container(border=True):
            st.markdown(f"**{name}**")

            if job.status == "error":
                st.markdown(badge("Failed", "error"), unsafe_allow_html=True)
                st.error(job.error)
                log_run(job.sops, status="Error", error=job.error)
                continue

            result = job.result
            pdf_path = job.pdf_path
            log_run(job.sops, status="Complete", result=result, pdf_path=pdf_path)

            st.markdown(badge("Complete", "complete"), unsafe_allow_html=True)

            if job.order and not st.session_state.get(f"delivered_{job.order.id}"):
                _deliver_to_order(job, pdf_path, result)

            with open(pdf_path, "rb") as f:
                st.download_button(
                    label=f"Download {name} report PDF",
                    data=f,
                    file_name=os.path.basename(pdf_path),
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True,
                    key=f"download_{i}",
                )

            with st.expander("Executive summary"):
                st.markdown(result.executive_summary)
                if result.cross_process:
                    st.markdown("#### Cross-process insights")
                    st.markdown(result.cross_process.insights)

    if st.button("Run another analysis", use_container_width=True):
        del st.session_state["jobs"]
        st.rerun()
