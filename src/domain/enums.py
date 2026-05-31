"""
Enumerations for the Bus Charging Scheduler.
All enums are defined here to avoid circular imports and provide
a single source of truth for categorical values.
"""
from enum import Enum


class Direction(str, Enum):
    """Travel direction for a bus trip."""
    BK = "BK"  # Bengaluru → Kochi
    KB = "KB"  # Kochi → Bengaluru


class EventType(str, Enum):
    """Types of simulation events processed by the event-driven engine."""
    BUS_DEPARTURE = "BUS_DEPARTURE"
    STATION_ARRIVAL = "STATION_ARRIVAL"
    CHARGING_STARTED = "CHARGING_STARTED"
    CHARGING_COMPLETED = "CHARGING_COMPLETED"
    TRIP_COMPLETED = "TRIP_COMPLETED"


class BusStatus(str, Enum):
    """Lifecycle states of a bus during simulation."""
    SCHEDULED = "SCHEDULED"       # Not yet departed
    EN_ROUTE = "EN_ROUTE"         # Travelling between stops
    WAITING = "WAITING"           # Queued for a charger
    CHARGING = "CHARGING"         # Currently charging
    COMPLETED = "COMPLETED"       # Reached final destination
    CANCELLED = "CANCELLED"       # Trip cancelled (future support)
