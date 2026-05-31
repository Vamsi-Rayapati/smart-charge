"""
Event dataclasses for the event-driven simulation engine.

Events are the fundamental unit of the scheduler. The engine processes
events chronologically, dispatching each to its handler.

All events are immutable dataclasses with a timestamp for heap ordering.
Events are comparable by timestamp (for the priority queue).

Event types and their meanings:
  BusDeparture      → A bus has left its origin depot, fully charged
  StationArrival    → A bus has reached a charging station
  ChargingStarted   → A bus has begun charging (charger acquired)
  ChargingCompleted → A bus has finished charging
  TripCompleted     → A bus has reached its final destination

Future events to add (no engine structural changes needed):
  TripCancelled     → A bus trip is cancelled mid-route
  ChargerOutage     → A charger becomes unavailable (replanning trigger)
  DelayNotification → A bus reports unexpected delay
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import ClassVar

from src.domain.enums import EventType


@dataclass(order=True)
class Event:
    """
    Base event class. Sortable by timestamp for min-heap priority queue.
    
    The `sort_index` field is used by the heap to order events.
    All subclasses set sort_index = timestamp automatically.
    """
    sort_index: float = field(init=False, repr=False)
    timestamp: float      # Minutes since midnight
    event_type: EventType
    bus_id: str

    def __post_init__(self):
        # Heap orders by sort_index; tie-break by bus_id for determinism
        self.sort_index = self.timestamp

    def __repr__(self) -> str:
        h = int(self.timestamp // 60) % 24
        m = int(self.timestamp % 60)
        return f"{self.event_type.value}[{self.bus_id}@{h:02d}:{m:02d}]"


@dataclass(order=True)
class BusDepartureEvent(Event):
    """Bus departs its origin depot, fully charged."""
    event_type: EventType = field(default=EventType.BUS_DEPARTURE, init=False)
    next_station_id: str = ""          # First charging station in the plan


@dataclass(order=True)
class StationArrivalEvent(Event):
    """Bus has arrived at a charging station."""
    event_type: EventType = field(default=EventType.STATION_ARRIVAL, init=False)
    station_id: str = ""
    distance_from_last: float = 0.0   # km since last charge/departure


@dataclass(order=True)
class ChargingStartedEvent(Event):
    """Bus has acquired the charger and started charging."""
    event_type: EventType = field(default=EventType.CHARGING_STARTED, init=False)
    station_id: str = ""
    wait_minutes: float = 0.0         # How long the bus waited before this


@dataclass(order=True)
class ChargingCompletedEvent(Event):
    """Bus has finished charging. Charger is released."""
    event_type: EventType = field(default=EventType.CHARGING_COMPLETED, init=False)
    station_id: str = ""
    next_station_id: str = ""         # Next charging stop, or destination if done
    is_final_leg: bool = False        # True if next stop is the destination


@dataclass(order=True)
class TripCompletedEvent(Event):
    """Bus has reached its final destination."""
    event_type: EventType = field(default=EventType.TRIP_COMPLETED, init=False)
    destination: str = ""
    total_wait_minutes: float = 0.0
