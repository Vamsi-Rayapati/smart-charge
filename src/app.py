# pyrefly: ignore [missing-import]
import streamlit as st

from src.services.scenario_loader import ScenarioLoader
from src.scheduler.engine import SchedulerEngine
from src.ui import (
    render_header,
    select_scenario,
    tune_weights,
    render_scenario_config,
    render_results,
    render_station_logs,
)

# Set page config for a premium wide layout with custom title
st.set_page_config(
    page_title="⚡ SmartCharge: Bus Charging Scheduler",
    page_icon="🚌",
    layout="wide",
    initial_sidebar_state="expanded",
)

render_header()

# Initialize scenario loader
loader = ScenarioLoader()
available = loader.available_scenarios()

if not available:
    st.error(
        "⚠️ No scenarios found in the `src/scenarios/` directory. "
        "Please ensure JSON files are present."
    )
    st.stop()

# Sidebar: scenario selection + live weight tuning
selected_id = select_scenario(available)
scenario = loader.load_by_id(selected_id)
scenario.weights = tune_weights(scenario)

# Run simulation engine
engine = SchedulerEngine()
result = engine.run(scenario)

# Main navigation tabs
tab1, tab2, tab3 = st.tabs([
    "📋 Scenario Configuration",
    "📊 Simulation Output & KPIs",
    "🔌 Charging Station Logs",
])

with tab1:
    render_scenario_config(scenario)

with tab2:
    render_results(result)

with tab3:
    render_station_logs(scenario, result)
