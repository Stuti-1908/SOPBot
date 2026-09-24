"""Password gate for operator-only access.

Session state alone doesn't survive a browser refresh - Streamlit resets
session_state on every new WebSocket connection, which a page reload
always creates, so the operator was being asked to log in again every
single refresh even seconds after logging in (a real reported issue,
not a hypothetical). Fixed by also persisting a signed, time-limited
token in the URL's query params: on login, a token is appended to the
URL; on load, that token is checked first before falling back to the
password form, so a refresh (same URL) stays logged in until the token
expires."""
import os
import time
import hmac
import hashlib
import streamlit as st

SESSION_TTL_SECONDS = 8 * 60 * 60  # 8 hours


def _secret() -> str:
    return os.environ.get("STREAMLIT_APP_PASSWORD", "")


def _check_password(entered: str) -> bool:
    correct = _secret()
    return hmac.compare_digest(entered.encode(), correct.encode())


def _make_token() -> str:
    """expiry.signature - HMAC over the expiry timestamp using the app
    password as the key, so a token can't be forged without knowing it,
    and naturally becomes invalid once STREAMLIT_APP_PASSWORD is rotated."""
    expiry = int(time.time()) + SESSION_TTL_SECONDS
    sig = hmac.new(_secret().encode(), str(expiry).encode(), hashlib.sha256).hexdigest()
    return f"{expiry}.{sig}"


def _token_is_valid(token: str) -> bool:
    try:
        expiry_str, sig = token.split(".", 1)
        expiry = int(expiry_str)
    except (ValueError, AttributeError):
        return False
    if time.time() > expiry:
        return False
    expected_sig = hmac.new(_secret().encode(), expiry_str.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected_sig)


def require_password() -> None:
    if st.session_state.get("authenticated"):
        return

    # Check the URL for a still-valid session token before showing the
    # login form - this is what makes a plain refresh (same URL) skip
    # re-entering the password.
    token = st.query_params.get("session")
    if token and _token_is_valid(token):
        st.session_state["authenticated"] = True
        return

    st.title("WorkflowIQ - Operator Login")
    pwd = st.text_input("Password", type="password")
    if st.button("Login"):
        if _check_password(pwd):
            st.session_state["authenticated"] = True
            st.query_params["session"] = _make_token()
            st.rerun()
        else:
            st.error("Incorrect password.")
            st.stop()
    else:
        st.stop()
