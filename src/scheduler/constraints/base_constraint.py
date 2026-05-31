"""
Abstract base class for all hard constraints.

Constraints are checked during plan enumeration. Any charging plan that
violates a constraint is rejected before simulation begins.

To add a new hard constraint:
1. Create a new module in scheduler/constraints/
2. Subclass Constraint
3. Register it in the ConstraintRegistry in engine.py

The engine never needs to change.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.models import Bus, Route, Scenario


class Constraint(ABC):
    """
    Pluggable hard constraint interface (Specification Pattern).
    
    All hard rules that MUST NEVER be violated implement this interface.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable constraint name for error messages."""
        ...

    @abstractmethod
    def is_satisfied(
        self,
        charging_stations: list[str],
        bus: "Bus",
        route: "Route",
        scenario: "Scenario",
    ) -> bool:
        """
        Return True if the proposed charging plan satisfies this constraint.

        Args:
            charging_stations: Ordered list of station IDs the bus plans to charge at.
            bus: The Bus object being planned for.
            route: The Route the bus is travelling on.
            scenario: The full scenario (for station lookups).
        """
        ...

    def violation_message(
        self,
        charging_stations: list[str],
        bus: "Bus",
        route: "Route",
        scenario: "Scenario",
    ) -> str:
        """Return a human-readable violation description."""
        return (
            f"Constraint '{self.name}' violated for bus '{bus.id}' "
            f"with plan {charging_stations}"
        )
