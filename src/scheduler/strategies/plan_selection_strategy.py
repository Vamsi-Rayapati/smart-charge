"""
PlanSelectionStrategy — Decides which charging plan a bus will execute.

PlanGenerator produces all feasible plans; this strategy picks one.
The strategy receives a SchedulerState snapshot at the bus's departure time,
so it can route around congestion that has already formed in the network.

To add a new strategy: subclass PlanSelectionStrategy, implement choose_plan().
No changes to SchedulerEngine required.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.models import Bus, Scenario


@dataclass
class SchedulerState:
    """
    Read-only snapshot of simulation state at plan-selection time.

    Passed to PlanSelectionStrategy so it can make an informed routing decision.
    Strategies must NOT mutate this object.
    """
    current_time: float
    # Buses already committed to charge at each station (cumulative, not real-time)
    station_usage: dict[str, int]
    # Buses currently waiting at each station right now
    waiting_queues: dict[str, list[str]]
    # Free-at timestamps per charger, per station: station_id → [t0, t1, ...]
    charger_slots: dict[str, list[float]]
    bus_cumulative_wait: dict[str, float]
    operator_total_wait: dict[str, float]
    operator_bus_counts: dict[str, int]
    network_total_wait: float


class PlanSelectionStrategy(ABC):
    """
    Selects one charging plan from the set of feasible candidates.

    Candidates are produced by PlanGenerator and are guaranteed to satisfy
    all hard constraints (battery, route order, charger capacity).
    """

    @abstractmethod
    def choose_plan(
        self,
        candidate_plans: list[list[str]],
        bus: "Bus",
        scenario: "Scenario",
        scheduler_state: SchedulerState,
    ) -> list[str]:
        """
        Choose one plan from candidate_plans.

        Args:
            candidate_plans: All feasible plans, sorted (fewest stops, then
                             lexicographic). Never empty — engine validates first.
            bus:             The bus being planned for.
            scenario:        Full scenario config (routes, stations, weights).
            scheduler_state: Live simulation state at the moment of selection.

        Returns: The chosen plan as an ordered list of station IDs.
        """


class FewestStopsStrategy(PlanSelectionStrategy):
    """
    Pick the plan with the fewest charging stops (original behavior).

    Candidates arrive pre-sorted by (len, stations), so this is plans[0].
    All buses with the same route get the same plan — useful as a baseline.
    """

    def choose_plan(
        self,
        candidate_plans: list[list[str]],
        bus: "Bus",
        scenario: "Scenario",
        scheduler_state: SchedulerState,
    ) -> list[str]:
        return candidate_plans[0]


class LoadBalancedStrategy(PlanSelectionStrategy):
    """
    Prefer plans whose stations are least committed across the fleet.

    Station load = number of buses already assigned to charge there.
    Plan score   = sum of load for every stop in the plan.

    Example:
        station_usage = {A: 10, B: 2, C: 8, D: 1}
        [A, C] → 18   (rejected)
        [A, D] → 11
        [B, D] →  3   ← chosen

    Tiebreak: fewest stops, then lexicographic (same as FewestStops).
    """

    def choose_plan(
        self,
        candidate_plans: list[list[str]],
        bus: "Bus",
        scenario: "Scenario",
        scheduler_state: SchedulerState,
    ) -> list[str]:
        def plan_load(plan: list[str]) -> tuple[int, int, list[str]]:
            load = sum(scheduler_state.station_usage.get(s, 0) for s in plan)
            return (load, len(plan), plan)

        return min(candidate_plans, key=plan_load)


class WeightedScoringStrategy(PlanSelectionStrategy):
    """
    Multi-factor plan scoring using the scenario's configured weights.

    Uses the same individual / operator / overall weight sliders that govern
    charger contention, keeping the UI consistent.

    Factor                  Weight          Measures
    ─────────────────────── ─────────────── ────────────────────────────────
    station_usage (avg)     individual      committed fleet load per stop
    queue_depth   (avg)     operator        buses currently waiting per stop
    expected_wait (avg)     overall         minutes until charger free per stop

    All factors are normalised per-stop so 2-stop and 3-stop plans are
    compared on equal footing.
    """

    def choose_plan(
        self,
        candidate_plans: list[list[str]],
        bus: "Bus",
        scenario: "Scenario",
        scheduler_state: SchedulerState,
    ) -> list[str]:
        weights = scenario.weights
        t = scheduler_state.current_time

        def plan_score(plan: list[str]) -> tuple[float, int]:
            n = len(plan)
            usage = sum(
                scheduler_state.station_usage.get(s, 0) for s in plan
            ) / n
            queue = sum(
                len(scheduler_state.waiting_queues.get(s, [])) for s in plan
            ) / n
            expected_wait = sum(
                max(0.0, max(scheduler_state.charger_slots.get(s, [0.0])) - t)
                for s in plan
            ) / n
            score = (
                weights.individual * usage
                + weights.operator * queue
                + weights.overall * expected_wait
            )
            return (score, n)  # tiebreak: fewest stops

        return min(candidate_plans, key=plan_score)
