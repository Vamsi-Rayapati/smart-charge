"""
TravelTimeStrategy — Strategy Pattern for travel time calculation.

Current: FixedSpeedStrategy computes travel_time = distance / bus.speed_kmh.
Future: TrafficAwareTravelStrategy can factor in real-time traffic, weather,
        road conditions using the same interface.

Speed is a per-bus property (bus.speed_kmh, default 60 km/h), not a global constant.
Mixed fleets (slow freight + fast express) work with no code changes.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.models import Bus


class TravelTimeStrategy(ABC):
    """
    Abstract interface for computing travel time between two stops.
    """

    @abstractmethod
    def travel_minutes(self, bus: "Bus", distance_km: float, context: dict) -> float:
        """
        Calculate travel time in minutes.
        
        Args:
            bus: The bus (has speed_kmh, potentially route_segment_id for traffic lookup)
            distance_km: Distance of the segment to travel
            context: Additional context (future: time_of_day, weather, traffic_factor)
        
        Returns: Travel time in minutes.
        """
        ...


class FixedSpeedStrategy(TravelTimeStrategy):
    """
    Current implementation: travel_time = distance_km / bus.speed_kmh * 60.
    
    Speed is per-bus (not a global constant), supporting mixed fleets.
    60 km/h on a 100 km segment = 100 minutes.
    """

    def travel_minutes(self, bus: "Bus", distance_km: float, context: dict) -> float:
        return (distance_km / bus.speed_kmh) * 60.0
