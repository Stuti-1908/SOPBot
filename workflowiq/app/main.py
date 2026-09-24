"""WorkflowIQ - Streamlit entry point."""
import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from app.auth import require_password
from app.theme import inject_css, render_header
from app.ui import render_ui

st.set_page_config(
    page_title="WorkflowIQ by DadaAI",
    page_icon="⚙️",
    layout="centered",
)

inject_css()
require_password()
render_header()
render_ui()
