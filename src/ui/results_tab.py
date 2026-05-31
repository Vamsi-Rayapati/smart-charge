"""Tab 2: simulation output — KPIs, timetable, and per-bus event timeline."""
# pyrefly: ignore [missing-import]
import streamlit as st
import pandas as pd

# Maps an event type to a presentation emoji.
_EVENT_EMOJI = {
    "DEPARTED": "🛫",
    "ARRIVED": "📥",
    "WAITING": "⏳",
    "CHARGING_STARTED": "🔌",
    "CHARGING_COMPLETED": "🔋",
}
_DEFAULT_EMOJI = "🏁"


def _event_emoji(event_type: str) -> str:
    return _EVENT_EMOJI.get(event_type, _DEFAULT_EMOJI)


def _event_color(event_type: str) -> str:
    """Pick a Streamlit markdown color name for the event's status badge."""
    if "COMPLETED" in event_type or "ARRIVED_DESTINATION" in event_type:
        return "green"
    if "WAITING" in event_type:
        return "orange"
    return "blue"


def render_kpis(result) -> None:
    """Render the four headline KPI metrics."""
    total_wait = result.total_network_wait_minutes
    active_buses = len(result.bus_timelines)
    avg_wait = total_wait / active_buses if active_buses > 0 else 0
    max_wait = max(
        (t.total_wait_minutes for t in result.bus_timelines.values()),
        default=0,
    )

    kpi_cols = st.columns(4)
    kpi_cols[0].metric("Total Fleet Wait Time", f"{total_wait:.1f} min")
    kpi_cols[1].metric("Average Wait Per Bus", f"{avg_wait:.1f} min")
    kpi_cols[2].metric("Peak Delay (Max Wait)", f"{max_wait:.1f} min")
    kpi_cols[3].metric("Active Bus Schedules", f"{active_buses}")


def render_timetable(result) -> None:
    """Render the fleet final timetable as a dataframe."""
    st.markdown("#### ⏰ Fleet Final Timetable")
    timetable_rows = []
    for bid, timeline in result.bus_timelines.items():
        bus = timeline.bus
        charging_sequence = " ➡️ ".join(
            stop.station_id for stop in timeline.charging_stops
        ) or "Non-Stop"
        timetable_rows.append({
            "Bus ID": bid,
            "Operator": bus.operator.upper(),
            "Direction": "BK" if bus.direction.value == "BK" else "KB",
            "Departure Time": bus.departure_time,
            "Arrival Time": timeline.final_arrival_hhmm,
            "Wait Time (min)": timeline.total_wait_minutes,
            "Charging Stops": charging_sequence,
            "Status": "✅ Completed" if timeline.completed else "❌ Failed",
        })
    st.dataframe(pd.DataFrame(timetable_rows), use_container_width=True)


def render_event_timeline(result) -> None:
    """Render the deep-dive per-bus event log for a selected bus."""
    st.markdown("#### 🔍 Deep-Dive: Individual Bus Event Timeline")
    selected_bus_id = st.selectbox(
        "Select a Bus to track detailed journey logs",
        list(result.bus_timelines.keys()),
    )
    if not selected_bus_id:
        return

    bt = result.bus_timelines[selected_bus_id]
    st.caption(
        f"Showing step-by-step travel logs for **{selected_bus_id}** "
        f"operated by **{bt.bus.operator.upper()}**:"
    )
    for ev in bt.events:
        emoji = _event_emoji(ev.event_type)
        color = _event_color(ev.event_type)
        with st.container(border=True):
            st.markdown(
                f"**{ev.time_hhmm}** {emoji} "
                f":{color}[**{ev.event_type}**] — *{ev.notes}*"
            )


def render_results(result) -> None:
    """Render the full simulation output tab."""
    st.markdown("### 📊 Simulation Analytics")
    render_kpis(result)
    st.write("")
    render_timetable(result)
    st.markdown("---")
    render_event_timeline(result)
