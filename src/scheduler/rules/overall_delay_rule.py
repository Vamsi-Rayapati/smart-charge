"""
OverallDelayRule — Soft Rule #3

Penalty: negative of total cumulative wait across ALL buses in the network.

Intent: when overall_weight is high, the scheduler tends to move buses
through chargers quickly to minimise total network suffering.

Note: since this penalty is the same for all competing buses at any
given moment, it acts as a global urgency multiplier. Buses competing
at a station when the network is suffering more will collectively
receive stronger priority pressure vs. FCFS. In practice, this rule's
differentiation power comes from its interaction with the other two rules
when weights vary across scenarios.

Scoring contribution:
  score += weights.overall * overall_penalty(bus)
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from .base_rule import ScoringRule, SimulationContext

if TYPE_CHECKING:
    from src.domain.models import Bus


class OverallDelayRule(ScoringRule):
    """
    Penalises based on total network wait, encouraging system-wide efficiency.
    
    When overall_weight is elevated, this magnifies the signal from the other
    rules — the scheduler becomes more aggressive about clearing queues.
    
    In Scenario 5 (worst-case convergence), total network wait spikes sharply
    at stations B and C. This rule ensures the engine prioritises throughput
    globally under that pressure.
    """

    @property
    def name(self) -> str:
        return "OverallDelayRule"

    def penalty(self, bus: "Bus", context: SimulationContext) -> float:
        """
        Returns negative of total network cumulative wait.
        
        Same value for all competing buses at a given moment — it serves as
        a global urgency amplifier that scales with total network congestion.
        """
        return -(context.network_total_wait)
