"""
RouteOrderConstraint — Hard Constraint #2

A bus must visit charging stations in route order — no backtracking.
The proposed charging plan must be a subsequence of the bus's ordered stops.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from .base_constraint import Constraint

if TYPE_CHECKING:
    from src.domain.models import Bus, Route, Scenario


class RouteOrderConstraint(Constraint):
    """
    Ensures charging stations are visited in the correct travel order.
    """

    @property
    def name(self) -> str:
        return "RouteOrderConstraint"

    def is_satisfied(
        self,
        charging_stations: list[str],
        bus: "Bus",
        route: "Route",
        scenario: "Scenario",
    ) -> bool:
        if not charging_stations:
            return True

        ordered_stops = route.ordered_stops_for_direction(bus.direction)
        # Only keep stops that are charging stations
        route_charging_stops = [
            s for s in ordered_stops if s in scenario.charging_station_ids
        ]

        # charging_stations must appear in the same relative order
        idx = 0
        for station in route_charging_stops:
            if idx < len(charging_stations) and station == charging_stations[idx]:
                idx += 1

        return idx == len(charging_stations)

    def violation_message(
        self,
        charging_stations: list[str],
        bus: "Bus",
        route: "Route",
        scenario: "Scenario",
    ) -> str:
        return (
            f"RouteOrderConstraint: Bus '{bus.id}' plan {charging_stations} "
            f"violates route order for direction {bus.direction.value}"
        )
