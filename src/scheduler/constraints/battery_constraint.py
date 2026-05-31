"""
BatteryConstraint — Hard Constraint #1

A bus can never travel more than battery_range_km between consecutive
charging events (or between start and first charge, or last charge and
destination).

This constraint is evaluated per-bus against a proposed charging plan
(an ordered list of station IDs the bus will charge at).

Future support:
- Per-bus battery_range_km already in Bus model → mixed fleets work now
- Dynamic range (battery degradation) can be plugged in via a RangeStrategy
  without changing this constraint class
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from .base_constraint import Constraint

if TYPE_CHECKING:
    from src.domain.models import Bus, Route, Scenario


class BatteryConstraint(Constraint):
    """
    Ensures no segment between consecutive charges exceeds the bus's range.
    """

    @property
    def name(self) -> str:
        return "BatteryConstraint"

    def is_satisfied(
        self,
        charging_stations: list[str],
        bus: "Bus",
        route: "Route",
        scenario: "Scenario",
    ) -> bool:
        """
        Check every inter-charge leg:
          origin → first_charge, charge_i → charge_i+1, last_charge → destination
        """
        ordered_stops = route.ordered_stops_for_direction(bus.direction)
        origin = ordered_stops[0]
        destination = ordered_stops[-1]

        # Build the full sequence of waypoints (charging + endpoints)
        waypoints = [origin] + charging_stations + [destination]

        for i in range(len(waypoints) - 1):
            try:
                leg_distance = route.distance_between(waypoints[i], waypoints[i + 1])
            except ValueError:
                # Stop not in route or wrong order
                return False

            if leg_distance > bus.battery_range_km:
                return False

        return True

    def violation_message(
        self,
        charging_stations: list[str],
        bus: "Bus",
        route: "Route",
        scenario: "Scenario",
    ) -> str:
        ordered_stops = route.ordered_stops_for_direction(bus.direction)
        origin = ordered_stops[0]
        destination = ordered_stops[-1]
        waypoints = [origin] + charging_stations + [destination]

        for i in range(len(waypoints) - 1):
            try:
                leg_distance = route.distance_between(waypoints[i], waypoints[i + 1])
            except ValueError:
                leg_distance = float("inf")
            if leg_distance > bus.battery_range_km:
                return (
                    f"BatteryConstraint: Bus '{bus.id}' would travel {leg_distance:.0f} km "
                    f"from '{waypoints[i]}' to '{waypoints[i+1]}' but range is "
                    f"{bus.battery_range_km:.0f} km"
                )
        return super().violation_message(charging_stations, bus, route, scenario)
