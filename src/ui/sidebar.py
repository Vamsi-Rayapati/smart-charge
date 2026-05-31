"""Sidebar controls: scenario selection and live weight tuning."""
# pyrefly: ignore [missing-import]
import streamlit as st

from src.domain.models import Scenario, Weights


def select_scenario(available: list[tuple[str, str]]) -> str:
    """Render the scenario picker and return the selected scenario id."""
    st.sidebar.markdown("## ⚙️ Scheduler Controls")
    scenario_options = {name: sid for sid, name in available}
    selected_name = st.sidebar.selectbox(
        "Select Simulation Scenario", list(scenario_options.keys())
    )
    return scenario_options[selected_name]


def tune_weights(scenario: Scenario) -> Weights:
    """Render the weight sliders and return the user-adjusted weights."""
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🎚️ Live Weight Optimization")
    st.sidebar.caption(
        "Fine-tune scheduling priority scores in real-time. "
        "The scheduler automatically recalculates wait-times."
    )
    w_individual = st.sidebar.slider(
        "Individual Wait Penalty Weight",
        0.0, 5.0, float(scenario.weights.individual), 0.5,
    )
    w_operator = st.sidebar.slider(
        "Operator Fairness Penalty Weight",
        0.0, 5.0, float(scenario.weights.operator), 0.5,
    )
    w_overall = st.sidebar.slider(
        "Overall Network Penalty Weight",
        0.0, 5.0, float(scenario.weights.overall), 0.5,
    )
    return Weights(
        individual=w_individual, operator=w_operator, overall=w_overall
    )
