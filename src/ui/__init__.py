"""UI sub-components for the SmartCharge Streamlit dashboard.

Each tab/section lives in its own module and is built from native Streamlit
elements (no raw HTML / unsafe_allow_html).
"""
from src.ui.header import render_header
from src.ui.sidebar import select_scenario, tune_weights
from src.ui.scenario_tab import render_scenario_config
from src.ui.results_tab import render_results
from src.ui.station_tab import render_station_logs

__all__ = [
    "render_header",
    "select_scenario",
    "tune_weights",
    "render_scenario_config",
    "render_results",
    "render_station_logs",
]
