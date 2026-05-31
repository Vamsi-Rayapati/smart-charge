"""
OperatorFairnessRule — Soft Rule #2

Penalty: negative of the average cumulative wait time for all buses
belonging to the same operator as this bus.

Intent: operators whose fleet is suffering more get priority.
When operator_weight is high (Scenario 4), the dominant operator KPN
faces a stronger fairness correction.

Scoring contribution:
  score += weights.operator * operator_fairness_penalty(bus)

Where:
  operator_fairness_penalty = -(fleet_avg_wait for bus.operator)
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from .base_rule import ScoringRule, SimulationContext

if TYPE_CHECKING:
    from src.domain.models import Bus


class OperatorFairnessRule(ScoringRule):
    """
    Penalises based on how much the bus's operator fleet has waited collectively.
    
    An operator whose average fleet wait is HIGH gets a more negative penalty,
    meaning lower score → higher priority at the charger.
    
    This makes Scenario 4 demonstrably different when operator_weight=2.0 vs 1.0:
    KPN dominates the fleet, so its high average wait gets amplified, pushing
    KPN buses to the front of queues when that weight is elevated.
    """

    @property
    def name(self) -> str:
        return "OperatorFairnessRule"

    def penalty(self, bus: "Bus", context: SimulationContext) -> float:
        """
        Returns negative of the fleet-average cumulative wait for bus.operator.
        
        Operators with higher average wait → more negative penalty → lower score → wins.
        """
        count = context.operator_bus_counts.get(bus.operator, 1)
        total_wait = context.operator_total_wait.get(bus.operator, 0.0)
        avg_wait = total_wait / max(count, 1)
        return -avg_wait
