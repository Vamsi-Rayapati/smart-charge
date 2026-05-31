"""
ChargerCapacityConstraint — Hard Constraint #3

One charger can serve one bus at a time. This is enforced dynamically
during simulation (not during plan validation), but the constraint class
is available for the framework to call at queue-resolution time.

The actual charger slot tracking lives in the engine's SimulationContext.
This constraint class validates that the proposed plan only targets known
stations that actually have chargers.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from .base_constraint import Constraint

if TYPE_CHECKING:
    from src.domain.models import Bus, Route, Scenario


class ChargerCapacityConstraint(Constraint):
    """
    Ensures all planned charging stations exist in the scenario and have chargers.
    
    Runtime exclusivity (one bus per charger) is enforced in the engine via
    the charger_free_at tracking list per station.
    """

    @property
    def name(self) -> str:
        return "ChargerCapacityConstraint"

    def is_satisfied(
        self,
        charging_stations: list[str],
        bus: "Bus",
        route: "Route",
        scenario: "Scenario",
    ) -> bool:
        valid_ids = set(scenario.charging_station_ids)
        return all(s in valid_ids for s in charging_stations)

    def violation_message(
        self,
        charging_stations: list[str],
        bus: "Bus",
        route: "Route",
        scenario: "Scenario",
    ) -> str:
        valid_ids = set(scenario.charging_station_ids)
        invalid = [s for s in charging_stations if s not in valid_ids]
        return (
            f"ChargerCapacityConstraint: Bus '{bus.id}' plan references "
            f"unknown stations: {invalid}"
        )
