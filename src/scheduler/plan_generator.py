"""
PlanGenerator — Enumerates all valid charging plans for a bus.

A charging plan is an ordered list of intermediate stations where the bus will charge.
A plan is VALID if it satisfies all registered Constraints.

For the Bengaluru→Kochi route (4 intermediate stations, 240 km range):
- Total distance: 540 km → minimum 2 charges required
- Valid 2-stop plans: (A,B), (A,C), (A,D), (B,C), (B,D), (C,D)
- Valid 3-stop plans: (A,B,C), (A,B,D), (A,C,D), (B,C,D)
- Valid 4-stop plans: (A,B,C,D)
- Filtered by BatteryConstraint → typically only a subset pass

The generator produces ALL valid plans for a bus, sorted by number of stops
(fewer stops preferred — less charging overhead). The engine then picks the
best plan based on scoring during conflict resolution.

Future: support partial replanning (bus already past station A →
        only consider remaining stations) via `from_stop` parameter.
"""
from __future__ import annotations
from itertools import combinations
from typing import TYPE_CHECKING

from src.scheduler.constraints.base_constraint import Constraint

if TYPE_CHECKING:
    from src.domain.models import Bus, Route, Scenario


class PlanGenerator:
    """
    Generates all valid charging plans for a bus given active constraints.
    
    Constraints are injected (not hardcoded), making it trivial to add
    new hard constraints without touching this class.
    """

    def __init__(self, constraints: list[Constraint]) -> None:
        self._constraints = constraints

    def generate_valid_plans(
        self,
        bus: "Bus",
        route: "Route",
        scenario: "Scenario",
    ) -> list[list[str]]:
        """
        Return all valid charging plans for this bus, sorted by plan length (ascending).
        
        Each plan is an ordered list of station IDs where the bus will charge.
        Plans are ordered shortest-first (fewest charges = least overhead).
        
        Args:
            bus: The bus to plan for
            route: The route the bus travels
            scenario: Full scenario (for station definitions)
        
        Returns: List of valid plans, each plan is a list of station IDs.
                 Empty list means no valid plan exists (constraint violation).
        """
        # Intermediate charging stations in travel order (not endpoints)
        chargeable = [
            s for s in route.stops
            if s in scenario.charging_station_ids
        ]

        valid_plans: list[list[str]] = []

        # Try all subset sizes from minimum required upward
        for size in range(1, len(chargeable) + 1):
            for combo in combinations(chargeable, size):
                plan = list(combo)
                if self._is_valid(plan, bus, route, scenario):
                    valid_plans.append(plan)

        # Sort by number of stops (fewest first), then lexicographically
        valid_plans.sort(key=lambda p: (len(p), p))
        return valid_plans

    def _is_valid(
        self,
        plan: list[str],
        bus: "Bus",
        route: "Route",
        scenario: "Scenario",
    ) -> bool:
        """Return True if the plan satisfies ALL registered constraints."""
        return all(
            c.is_satisfied(plan, bus, route, scenario)
            for c in self._constraints
        )

    def best_plan(
        self,
        bus: "Bus",
        route: "Route",
        scenario: "Scenario",
    ) -> list[str]:
        """
        Return the single best valid plan for this bus.
        
        'Best' = fewest charging stops (lowest overhead).
        Ties are broken by earliest stations (prefer charging earlier in trip).
        
        Raises ValueError if no valid plan exists.
        """
        plans = self.generate_valid_plans(bus, route, scenario)
        if not plans:
            raise ValueError(
                f"No valid charging plan found for bus '{bus.id}' "
                f"(route={bus.route_id}, range={bus.battery_range_km} km). "
                f"Check route distances and battery range."
            )
        return plans[0]
