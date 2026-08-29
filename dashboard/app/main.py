"""SOPBot Owner Dashboard — Streamlit entry point."""
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from app.ui import render_ui

st.set_page_config(
    page_title="SOPBot Dashboard",
    page_icon="📋",
    layout="centered",
)

render_ui()
