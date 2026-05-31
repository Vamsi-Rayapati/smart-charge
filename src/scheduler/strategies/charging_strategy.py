"""
ChargingStrategy — Strategy Pattern for charging duration calculation.

Current: FixedChargingStrategy always returns bus.charging_duration_minutes (default 25).
Future: DynamicChargingStrategy can compute duration based on battery_pct,
        charger_power_kw, temperature, battery_health, etc.

To switch strategies: change "charging_strategy": "dynamic" in the scenario JSON.
No engine changes required.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.models import Bus, Station


class ChargingStrategy(ABC):
    """
    Abstract interface for charging duration calculation.
    
    Implementations encapsulate the formula for how long a bus takes
    to charge at a given station under given conditions.
    """

    @abstractmethod
    def duration_minutes(self, bus: "Bus", station: "Station", context: dict) -> float:
        """
        Calculate charging duration in minutes.
        
        Args:
            bus: The bus being charged (has battery_range_km, charging_duration_minutes)
            station: The station providing the charge (future: charger_power_kw)
            context: Additional context dict (future: battery_pct, temperature, etc.)
        
        Returns: Duration in minutes as a float.
        """
        ...


class FixedChargingStrategy(ChargingStrategy):
    """
    Current implementation: always charges for bus.charging_duration_minutes (default 25).
    
    The value comes from the bus model, not hardcoded here. So:
    - Change a bus's charging_duration_minutes in JSON → different duration
    - Different bus types can have different fixed durations
    - This strategy stays unchanged
    """

    def duration_minutes(self, bus: "Bus", station: "Station", context: dict) -> float:
        return bus.charging_duration_minutes
