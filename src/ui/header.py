"""App header component."""
# pyrefly: ignore [missing-import]
import streamlit as st


def render_header() -> None:
    """Render the dashboard title and subtitle via native elements."""
    st.title("⚡ SmartCharge Dashboard")
    st.caption(
        "Production-Ready Event-Driven Electric Bus Fleet "
        "Charging & Dispatch Scheduler"
    )
