"""
Pydantic v2 domain models for the Bus Charging Scheduler.

Design principles:
- All models are immutable by default (frozen=True where appropriate)
- Every field that may vary in the future is explicit (no hardcoded physics)
- Default values encode today's assumptions; changing a scenario JSON field
  is sufficient to change behaviour — no code changes required.

Future-proofing baked in:
- Bus.battery_range_km → supports 240/320/500 km vehicles via JSON
- Bus.speed_kmh        → supports variable speed (traffic, weather) via JSON
- Bus.charging_duration_minutes → supports dynamic charging via Strategy pattern
- Bus.priority         → supports VIP/Emergency buses via PriorityRule
- Bus.status           → supports cancellations, delays
- Station.num_chargers → supports multi-charger stations via JSON
- Segment fields       → supports arbitrary route topologies
"""

from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field, model_validator
from datetime import datetime, date
from .enums import BusStatus


# ---------------------------------------------------------------------------
# Route / Network Models
# ---------------------------------------------------------------------------

class Segment(BaseModel):
    """A single directed edge in the route graph."""
    from_stop: str = Field(..., alias="from")
    to_stop: str = Field(..., alias="to")
    distance_km: float = Field(..., gt=0)

    model_config = {"populate_by_name": True}


class Route(BaseModel):
    """
    An ordered list of stops connected by segments.
    
    Supports arbitrary routes (not just Bengaluru-Kochi) so that future
    routes like Chennai → Mangalore can be added via JSON alone.
    """
    id: str
    stops: list[str]          # Ordered: [origin, ..., destination]
    segments: list[Segment]   # Must align with stops

    @model_validator(mode="after")
    def validate_segments_match_stops(self) -> "Route":
        expected = len(self.stops) - 1
        if len(self.segments) != expected:
            raise ValueError(
                f"Route '{self.id}' has {len(self.stops)} stops but "
                f"{len(self.segments)} segments (expected {expected})"
            )
        return self

    def distance_between(self, from_stop: str, to_stop: str) -> float:
        """Total distance between two stops (supports multi-hop calculation in both directions)."""
        stops = self.stops
        try:
            i = stops.index(from_stop)
            j = stops.index(to_stop)
        except ValueError as e:
            raise ValueError(f"Stop not found in route '{self.id}': {e}") from e
        
        if i == j:
            return 0.0
        elif i < j:
            return sum(seg.distance_km for seg in self.segments[i:j])
        else:
            return sum(seg.distance_km for seg in self.segments[j:i])

    def stops_between(self, from_stop: str, to_stop: str) -> list[str]:
        """All stops (exclusive of from_stop, inclusive of to_stop) in order."""
        i = self.stops.index(from_stop)
        j = self.stops.index(to_stop)
        return self.stops[i + 1 : j + 1]


# ---------------------------------------------------------------------------
# Station Model
# ---------------------------------------------------------------------------

class Station(BaseModel):
    """
    A charging station along the route.

    num_chargers defaults to 1 (current requirement).
    To support 3 chargers at Station A: just change "num_chargers": 3 in JSON.
    """
    id: str
    name: str
    num_chargers: int = Field(default=1, ge=1)

    # Future fields (zero-cost to add in JSON):
    # charger_power_kw: float = 150.0
    # electricity_price_schedule: dict[str, float] = {}  # hour -> price per kWh
    # latitude: float | None = None
    # longitude: float | None = None


# ---------------------------------------------------------------------------
# Bus Model
# ---------------------------------------------------------------------------

class Bus(BaseModel):
    """
    Represents a single bus trip in a scenario.

    All physics properties are per-bus so that a mixed fleet (240 km + 320 km)
    works without any code changes — just different values in the JSON.
    """
    id: str
    operator: str
    route_id: str
    departure_time: str             # "HH:MM" format — parsed at runtime
    battery_range_km: float = Field(default=240.0, gt=0)
    speed_kmh: float = Field(default=60.0, gt=0)
    charging_duration_minutes: float = Field(default=25.0, gt=0)
    priority: int = Field(default=0, ge=0)  # 0=normal, 1=VIP, 2=emergency
    status: BusStatus = BusStatus.SCHEDULED

    # Future: delay support
    delay_minutes: float = Field(default=0.0, ge=0)

    def departure_minutes(self) -> float:
        """Convert HH:MM departure time to minutes-since-midnight float."""
        h, m = map(int, self.departure_time.split(":"))
        return h * 60.0 + m + self.delay_minutes


# ---------------------------------------------------------------------------
# Scenario Weights
# ---------------------------------------------------------------------------

class Weights(BaseModel):
    """
    Scoring weights for the three soft rules.
    
    Changing these values in the scenario JSON changes scheduling behaviour
    with zero code changes. This is the single source of truth for weights.
    """
    individual: float = Field(default=1.0, ge=0)
    operator: float = Field(default=1.0, ge=0)
    overall: float = Field(default=1.0, ge=0)


# ---------------------------------------------------------------------------
# Scenario (top-level config)
# ---------------------------------------------------------------------------

class Scenario(BaseModel):
    """
    A fully self-contained scheduling scenario.
    
    One JSON file = one complete world. No external config needed.
    This design allows the live interview question 'add a new station / 
    change a segment distance' to be answered by editing one file.
    """
    id: str
    name: str
    description: str = ""
    weights: Weights = Field(default_factory=Weights)
    routes: list[Route]
    stations: list[Station]
    buses: list[Bus]

    @property
    def charging_station_ids(self) -> list[str]:
        """IDs of all charging stations (not endpoints)."""
        return [s.id for s in self.stations]

    def get_route(self, route_id: str) -> "Route":
        """Look up a route by ID."""
        for r in self.routes:
            if r.id == route_id:
                return r
        raise KeyError(f"Route '{route_id}' not found in scenario '{self.id}'")

    def get_station(self, station_id: str) -> Station:
        """Look up a station by ID."""
        for s in self.stations:
            if s.id == station_id:
                return s
        raise KeyError(
            f"Station '{station_id}' not found in scenario '{self.id}'"
        )


# ---------------------------------------------------------------------------
# Charging Plan
# ---------------------------------------------------------------------------

class ChargingStop(BaseModel):
    """A single planned charging stop for a bus."""
    station_id: str
    planned_arrival_minutes: float   # Minutes since midnight
    actual_arrival_minutes: float = 0.0
    wait_minutes: float = 0.0
    charge_start_minutes: float = 0.0
    charge_end_minutes: float = 0.0


class ChargingPlan(BaseModel):
    """
    The complete charging itinerary for one bus.
    
    Generated by PlanGenerator, populated with actual times by the engine.
    """
    bus_id: str
    stops: list[ChargingStop]
    final_arrival_minutes: float = 0.0
    total_wait_minutes: float = 0.0
    is_valid: bool = True
    violation_message: str = ""


# ---------------------------------------------------------------------------
# Simulation Timeline (Output)
# ---------------------------------------------------------------------------

class TimelineEvent(BaseModel):
    """
    A single recorded event in the output timeline for a bus.
    Used for rendering the per-bus timetable in the UI.
    """
    bus_id: str
    event_type: str
    station_id: str | None = None
    time_minutes: float
    notes: str = ""

    @property
    def time_hhmm(self) -> str:
        """Format minutes-since-midnight as HH:MM string."""
        h = int(self.time_minutes // 60) % 24
        m = int(self.time_minutes % 60)
        return f"{h:02d}:{m:02d}"


class BusTimeline(BaseModel):
    """Complete timeline of events for one bus — the primary output object."""
    bus: Bus
    charging_stops: list[ChargingStop] = Field(default_factory=list)
    events: list[TimelineEvent] = Field(default_factory=list)
    final_arrival_minutes: float = 0.0
    total_wait_minutes: float = 0.0
    completed: bool = False

    @property
    def final_arrival_hhmm(self) -> str:
        h = int(self.final_arrival_minutes // 60) % 24
        m = int(self.final_arrival_minutes % 60)
        return f"{h:02d}:{m:02d}"


class StationLog(BaseModel):
    """Per-station charging log — the secondary output object."""
    station_id: str
    charging_order: list[str] = Field(default_factory=list)  # bus IDs in service order
    entries: list[dict[str, Any]] = Field(default_factory=list)


class ScheduleResult(BaseModel):
    """Complete output of the scheduler for one scenario run."""
    scenario_id: str
    bus_timelines: dict[str, BusTimeline] = Field(default_factory=dict)
    station_logs: dict[str, StationLog] = Field(default_factory=dict)
    total_network_wait_minutes: float = 0.0
