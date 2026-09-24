"""Brand theming for the WorkflowIQ operator tool.

Reuses the exact palette already established across the marketing site,
dashboard, and transactional emails (see marketing/assets/style.css) rather
than inventing a new one - this is one product family, and an operator
switching between the dashboard and this tool all day should not feel like
they've landed on a different, unrelated app.

.streamlit/config.toml sets the base widget colors Streamlit itself
controls (buttons, inputs, sidebar). This module injects CSS for the
things config.toml can't reach: the branded header, card containers,
status badges, and typography.
"""
import streamlit as st

GROUND = "#FAF6EF"
GROUND_RAISED = "#F3ECDF"
INK = "#241F1A"
INK_SOFT = "#5C5348"
INK_FAINT = "#9B9184"
ACCENT = "#C1602A"
ACCENT_SOFT = "#E8DDCC"
CONFIRM = "#5E7C5A"
CONFIRM_SOFT = "#E1E9DD"
WARN = "#B3452D"
WARN_SOFT = "#F3D9C4"
RULE = "#E3D9C6"


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Work+Sans:wght@400;500;600&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Work Sans', -apple-system, BlinkMacSystemFont, sans-serif;
        }}

        .block-container {{
            padding-top: 2rem;
            max-width: 760px;
        }}

        h1, h2, h3 {{
            font-family: 'Fraunces', Georgia, serif !important;
            color: {INK} !important;
        }}

        .wiq-header {{
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            padding-bottom: 4px;
            margin-bottom: 8px;
        }}
        .wiq-header .wordmark {{
            font-family: 'Fraunces', Georgia, serif;
            font-size: 1.9rem;
            font-weight: 600;
            color: {INK};
        }}
        .wiq-header .wordmark span {{ color: {ACCENT}; }}
        .wiq-header .tagline {{
            font-size: 0.85rem;
            color: {INK_FAINT};
        }}

        .wiq-card {{
            background: {GROUND_RAISED};
            border: 1px solid {RULE};
            border-radius: 8px;
            padding: 20px 24px;
            margin-bottom: 16px;
        }}
        .wiq-card-label {{
            font-size: 0.8rem;
            font-weight: 600;
            color: {ACCENT};
            margin-bottom: 6px;
        }}

        .wiq-badge {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 600;
        }}
        .wiq-badge-pending {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}
        .wiq-badge-running {{ background: {ACCENT_SOFT}; color: {ACCENT}; }}
        .wiq-badge-complete {{ background: {CONFIRM_SOFT}; color: {CONFIRM}; }}
        .wiq-badge-error {{ background: {WARN_SOFT}; color: {WARN}; }}

        div[data-testid="stButton"] button[kind="primary"] {{
            background-color: {ACCENT};
            border-color: {ACCENT};
            font-weight: 600;
        }}
        div[data-testid="stButton"] button[kind="primary"]:hover {{
            background-color: #A64F21;
            border-color: #A64F21;
        }}

        hr {{ border-color: {RULE} !important; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    st.markdown(
        f"""
        <div class="wiq-header">
            <div>
                <div class="wordmark">WorkflowIQ<span>.</span></div>
                <div class="tagline">Process optimisation reports, powered by DadaAI</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def badge(text: str, kind: str) -> str:
    """kind: pending | running | complete | error"""
    return f'<span class="wiq-badge wiq-badge-{kind}">{text}</span>'
