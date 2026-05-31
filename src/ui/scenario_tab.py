"""Tab 1: scenario configuration view (routes, stations, fleet)."""
# pyrefly: ignore [missing-import]
import streamlit as st
import pandas as pd

from src.domain.models import Scenario


def _route_table(scenario: Scenario) -> None:
    st.markdown("#### 📍 Route Topology")
    for route in scenario.routes:
        st.markdown(f"**{route.stops[0]} → {route.stops[-1]}** (`{route.id}`)")
        route_df = pd.DataFrame([
            {
                "From": seg.from_stop,
                "To": seg.to_stop,
                "Distance (km)": f"{seg.distance_km} km",
            }
            for seg in route.segments
        ])
        st.table(route_df)


def _stations_table(scenario: Scenario) -> None:
    st.markdown("#### ⚡ Charging Stations Infrastructure")
    stations_df = pd.DataFrame([
        {
            "Station ID": s.id,
            "Station Name": s.name,
            "Available Chargers": s.num_chargers,
        }
        for s in scenario.stations
    ])
    st.dataframe(stations_df, use_container_width=True)


def _fleet_table(scenario: Scenario) -> None:
    st.markdown("#### 🚌 Fleet Deparature & Configuration")
    buses_data = []
    for b in scenario.buses:
        route = scenario.get_route(b.route_id)
        direction_label = f"{route.stops[0]} → {route.stops[-1]}"
        priority = (
            "🔴 Emergency" if b.priority == 2
            else "🟡 VIP" if b.priority == 1
            else "🟢 Normal"
        )
        buses_data.append({
            "Bus ID": b.id,
            "Operator": b.operator.upper(),
            "Route": direction_label,
            "Departure": b.departure_time,
            "Range (km)": f"{b.battery_range_km} km",
            "Speed (km/h)": f"{b.speed_kmh} km/h",
            "Priority": priority,
        })
    st.dataframe(pd.DataFrame(buses_data), use_container_width=True)


def render_scenario_config(scenario: Scenario) -> None:
    """Render the fleet & infrastructure configuration tab."""
    st.markdown("### 🚍 Fleet & Infrastructure Settings")
    st.info(f"**Description:** {scenario.description}")

    col1, col2 = st.columns(2)
    with col1:
        _route_table(scenario)
        _stations_table(scenario)
    with col2:
        _fleet_table(scenario)
