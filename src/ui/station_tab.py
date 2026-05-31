"""Tab 3: charging station activity logs."""
# pyrefly: ignore [missing-import]
import streamlit as st

from src.domain.models import Scenario


def _render_station(station, result) -> None:
    st.markdown(f"#### 🚉 {station.name}")
    log = result.station_logs.get(station.id)
    if not (log and log.entries):
        st.info("No charging events registered.")
        return

    st.success(f"Served {len(log.entries)} bus(es)")
    for entry in log.entries:
        with st.container(border=True):
            bus_id = entry["bus_id"]
            operator = entry["operator"].upper()
            st.markdown(f"**🚌 {bus_id}** ({operator})")
            st.caption(f"Completed charge at **{entry['charge_end']}**")


def render_station_logs(scenario: Scenario, result) -> None:
    """Render one column per station with its chronological charge log."""
    st.markdown("### 🔌 Charging Station Activity logs")
    st.caption(
        "Review chronological charger utility rates and queuing "
        "logs per station stop."
    )
    cols = st.columns(len(scenario.stations))
    for idx, station in enumerate(scenario.stations):
        with cols[idx]:
            _render_station(station, result)
