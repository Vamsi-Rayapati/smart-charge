"""
IndividualWaitRule — Soft Rule #1

Penalty: total cumulative wait time this bus has accumulated so far.

Intent: no single bus should wait too long. A bus that has already
waited 20 minutes has a higher penalty → it earns priority at the
next contention point.

Scoring contribution:
  score += weights.individual * bus.cumulative_wait_minutes
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from .base_rule import ScoringRule, SimulationContext

if TYPE_CHECKING:
    from src.domain.models import Bus


class IndividualWaitRule(ScoringRule):
    """
    Penalises buses proportionally to how long they have already waited.
    
    A bus with more accumulated wait has a HIGHER penalty, meaning it gets
    LOWER score → it jumps the queue and receives priority.
    
    Note: 'lower score wins' is the convention in ScoringStrategy.
    """

    @property
    def name(self) -> str:
        return "IndividualWaitRule"

    def penalty(self, bus: "Bus", context: SimulationContext) -> float:
        """
        Returns the cumulative wait time (in minutes) for this bus.
        
        A bus that has waited a lot earns a HIGH penalty under this rule,
        which (because lower score wins) gives it priority.
        
        Wait: this seems backwards — shouldn't MORE penalty mean LESS priority?
        
        Resolution: The scoring formula is:
          score = w_ind * individual_penalty + w_op * op_penalty + w_overall * overall_penalty
        And LOWER score wins. So when individual_penalty is HIGH for a bus,
        its score is HIGH → it loses.
        
        To actually give priority to long-waiting buses, we return the
        NEGATIVE of cumulative wait, so buses that waited more get a
        LOWER (more negative) score → they WIN.
        
        This is the standard "priority inversion" for min-heap priority queues.
        """
        return -(context.bus_cumulative_wait.get(bus.id, 0.0))
