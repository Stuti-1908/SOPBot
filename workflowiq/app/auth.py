"""Simple password gate for operator-only access."""
import os
import hmac
import streamlit as st


def _check_password(entered: str) -> bool:
    correct = os.environ.get("STREAMLIT_APP_PASSWORD", "")
    return hmac.compare_digest(entered.encode(), correct.encode())


def require_password() -> None:
    if st.session_state.get("authenticated"):
        return

    st.title("WorkflowIQ — Operator Login")
    pwd = st.text_input("Password", type="password")
    if st.button("Login"):
        if _check_password(pwd):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
            st.stop()
    else:
        st.stop()
