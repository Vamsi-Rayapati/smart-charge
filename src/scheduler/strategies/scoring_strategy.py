"""
ScoringStrategy — Aggregates all rules with configurable weights.

This is the single place where weights are applied. The weights come
from the Scenario's Weights model (which comes from the scenario JSON).

To change weights: edit the JSON. No code changes.
To add a rule: subclass ScoringRule, register below. No engine changes.

The formula:
  score(bus) = sum(rule.weight * rule.penalty(bus, context) for rule in rules)

Lower score → higher priority → wins the charger.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from ..rules.base_rule import ScoringRule, SimulationContext
from ..rules.individual_wait_rule import IndividualWaitRule
from ..rules.operator_fairness_rule import OperatorFairnessRule
from ..rules.overall_delay_rule import OverallDelayRule

if TYPE_CHECKING:
    from src.domain.models import Bus, Weights


class ScoringStrategy:
    """
    Composes all active scoring rules with their configured weights.
    
    Instantiated once per scenario run with that scenario's Weights.
    Rules are stateless — the context carries all mutable state.
    """

    def __init__(self, weights: "Weights") -> None:
        self._weights = weights
        # Rule registry: (rule_instance, weight_accessor)
        self._rules: list[tuple[ScoringRule, float]] = [
            (IndividualWaitRule(), weights.individual),
            (OperatorFairnessRule(), weights.operator),
            (OverallDelayRule(), weights.overall),
        ]

    def score(self, bus: "Bus", context: SimulationContext) -> float:
        """
        Compute the composite score for a bus at this decision point.
        
        Lower score = higher priority = wins charger contention.
        
        Each rule's penalty() can return positive or negative values;
        the convention is: negative penalty = good for the bus.
        """
        return sum(weight * rule.penalty(bus, context) for rule, weight in self._rules)

    def rank_queue(
        self, waiting_buses: list["Bus"], context: SimulationContext
    ) -> list["Bus"]:
        """
        Return waiting buses sorted by score ascending (lowest score first = highest priority).
        """
        return sorted(waiting_buses, key=lambda b: self.score(b, context))

    @property
    def active_rules(self) -> list[str]:
        """Names of all active rules — useful for documentation and debugging."""
        return [rule.name for rule, _ in self._rules]
