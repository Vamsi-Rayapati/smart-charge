"""
Abstract base class for all soft scoring rules.

Rules implement the Rule Engine pattern. Each rule computes a penalty
for a given bus at a decision point. The ScoringStrategy aggregates
all rules using configurable weights from the scenario JSON.

To add a new rule (e.g., PriorityBusRule, ElectricityCostRule):
1. Create a new module in scheduler/rules/
2. Subclass ScoringRule and implement penalty()
3. Register it in the rule factory in scoring_strategy.py

The engine, the constraints, and all other rules are UNCHANGED.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.models import Bus, Scenario


@dataclass
class SimulationContext:
    """
    Read-only snapshot of simulation state at the moment of scoring.
    
    Passed to every rule's penalty() method. Rules must NOT mutate this.
    This is the data contract between the engine and the rule engine.
    """
    current_time: float                        # Minutes since midnight
    bus_cumulative_wait: dict[str, float]      # bus_id → total wait so far
    operator_bus_counts: dict[str, int]        # operator → total buses in scenario
    operator_total_wait: dict[str, float]      # operator → cumulative wait for fleet
    network_total_wait: float                  # Sum of all bus waits so far
    station_queue_length: dict[str, int]       # station_id → current queue size


class ScoringRule(ABC):
    """
    A pluggable soft constraint / scoring rule.
    
    Each rule returns a non-negative penalty value. Lower penalty = higher priority.
    The weight for each rule comes from the scenario's Weights config — never hardcoded.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable rule name."""
        ...

    @abstractmethod
    def penalty(self, bus: "Bus", context: SimulationContext) -> float:
        """
        Compute the penalty for this bus at this moment.
        
        Returns: float >= 0. Higher = more penalty = lower priority when scoring.
        """
        ...
