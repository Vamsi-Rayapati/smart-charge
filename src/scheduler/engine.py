"""
SchedulerEngine — Core event-driven simulation engine.

Algorithm:
  Phase 1 — Seeding:
    Push a BusDeparture event for every active bus.
    No plans are assigned yet — selection is deferred to departure time
    so each bus sees the real network state when it actually leaves.

  Phase 2 — Event-Driven Simulation:
    Process events chronologically from a min-heap priority queue:

    BusDeparture     → select plan via PlanSelectionStrategy
                       → push StationArrival for first charging stop
    StationArrival   → if charger free: start charging immediately
                       → else: add bus to waiting queue
    ChargingStarted  → record in timeline
    ChargingCompleted→ release charger slot
                       → serve next waiting bus (scored by rules)
                       → push next event (next station or destination)
    TripCompleted    → record final arrival

  Charger State:
    charger_slots[station_id]: one float per charger (free-at timestamp).
    Supports num_chargers > 1 transparently.

  Conflict Resolution:
    Waiting buses are scored by ScoringStrategy; lowest score wins.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass

from src.domain.models import (
    Scenario, Bus, BusTimeline, StationLog,
    ScheduleResult, ChargingStop, TimelineEvent,
)
from src.scheduler.events.event import (
    BusDepartureEvent, StationArrivalEvent,
    ChargingStartedEvent, ChargingCompletedEvent, TripCompletedEvent,
)
from src.scheduler.events.event_queue import EventQueue
from src.scheduler.rules.base_rule import SimulationContext
from src.scheduler.strategies.charging_strategy import (
    ChargingStrategy, FixedChargingStrategy,
)
from src.scheduler.strategies.travel_time_strategy import (
    TravelTimeStrategy, FixedSpeedStrategy,
)
from src.scheduler.strategies.scoring_strategy import ScoringStrategy
from src.scheduler.strategies.plan_selection_strategy import (
    PlanSelectionStrategy, LoadBalancedStrategy, SchedulerState,
)
from src.scheduler.constraints.battery_constraint import BatteryConstraint
from src.scheduler.constraints.charger_constraint import (
    ChargerCapacityConstraint,
)
from src.scheduler.constraints.route_constraint import RouteOrderConstraint
from src.scheduler.plan_generator import PlanGenerator


@dataclass
class BusState:
    """All mutable runtime state for a single bus during simulation."""
    bus: Bus
    plan: list[str]             # Ordered charging station IDs
    plan_index: int = 0         # Index of the stop we are heading to next
    cumulative_wait: float = 0.0
    last_position: str = ""
    last_position_time: float = 0.0


class SchedulerEngine:
    """
    Event-driven bus charging scheduler.

    Wires together PlanGenerator, PlanSelectionStrategy, EventQueue,
    ScoringStrategy, ChargingStrategy, and TravelTimeStrategy.

    Adding rules, constraints, or strategies never requires modifying
    this file.
    """

    def __init__(
        self,
        charging_strategy: ChargingStrategy | None = None,
        travel_time_strategy: TravelTimeStrategy | None = None,
        plan_selection_strategy: PlanSelectionStrategy | None = None,
    ) -> None:
        self._charging_strategy = (
            charging_strategy or FixedChargingStrategy()
        )
        self._travel_strategy = (
            travel_time_strategy or FixedSpeedStrategy()
        )
        self._plan_selection_strategy = (
            plan_selection_strategy or LoadBalancedStrategy()
        )
        self._constraints = [
            BatteryConstraint(),
            RouteOrderConstraint(),
            ChargerCapacityConstraint(),
        ]
        self._plan_generator = PlanGenerator(self._constraints)

    def run(self, scenario: Scenario) -> ScheduleResult:
        """Execute the simulation and return the complete schedule result."""
        scoring = ScoringStrategy(scenario.weights)
        queue = EventQueue()

        # --- State dicts ---
        bus_states: dict[str, BusState] = {}
        timelines: dict[str, BusTimeline] = {}
        station_logs: dict[str, StationLog] = {
            s.id: StationLog(station_id=s.id) for s in scenario.stations
        }

        # One free-at timestamp per charger, per station
        charger_slots: dict[str, list[float]] = {
            s.id: [0.0] * s.num_chargers for s in scenario.stations
        }

        # Buses committed to charge at each station (for load balancing)
        station_usage: dict[str, int] = defaultdict(int)

        # Waiting queues: station_id → bus_ids in arrival order
        waiting_queues: dict[str, list[str]] = defaultdict(list)

        # (bus_id, station_id) → arrival timestamp
        arrival_times: dict[tuple[str, str], float] = {}

        bus_cumulative_wait: dict[str, float] = {}
        operator_total_wait: dict[str, float] = defaultdict(float)
        operator_bus_counts: dict[str, int] = defaultdict(int)
        network_total_wait: float = 0.0

        # --- Count operators ---
        for bus in scenario.buses:
            if bus.status.value == "CANCELLED":
                continue
            operator_bus_counts[bus.operator] += 1
            bus_cumulative_wait[bus.id] = 0.0

        # --- Phase 1: Seed departure events (plans assigned lazily) ---
        for bus in scenario.buses:
            if bus.status.value == "CANCELLED":
                continue

            bus_route = scenario.get_route(bus.route_id)
            origin = bus_route.stops[0]

            bus_states[bus.id] = BusState(
                bus=bus,
                plan=[],            # filled in when BusDeparture fires
                last_position=origin,
                last_position_time=bus.departure_minutes(),
            )
            timelines[bus.id] = BusTimeline(bus=bus)

            queue.push(BusDepartureEvent(
                timestamp=bus.departure_minutes(),
                bus_id=bus.id,
                next_station_id="",     # resolved at departure time
            ))

        # --- Phase 2: Event loop ---
        while not queue.is_empty():
            event = queue.pop()
            bus_id = event.bus_id

            if bus_id not in bus_states:
                continue

            state = bus_states[bus_id]
            bus = state.bus

            def make_context(t: float) -> SimulationContext:
                return SimulationContext(
                    current_time=t,
                    bus_cumulative_wait=dict(bus_cumulative_wait),
                    operator_bus_counts=dict(operator_bus_counts),
                    operator_total_wait=dict(operator_total_wait),
                    network_total_wait=network_total_wait,
                    station_queue_length={
                        sid: len(q)
                        for sid, q in waiting_queues.items()
                    },
                )

            # ---- BusDeparture ----
            if isinstance(event, BusDepartureEvent):
                bus_route = scenario.get_route(bus.route_id)
                origin = bus_route.stops[0]

                # Select plan lazily: strategy sees real network state now
                candidates = self._plan_generator.generate_valid_plans(
                    bus, bus_route, scenario
                )
                if not candidates:
                    raise ValueError(
                        f"No valid charging plan for bus '{bus.id}' "
                        f"(route={bus.route_id}, "
                        f"range={bus.battery_range_km} km)."
                    )

                sel_state = SchedulerState(
                    current_time=event.timestamp,
                    station_usage=dict(station_usage),
                    waiting_queues={
                        sid: list(q)
                        for sid, q in waiting_queues.items()
                    },
                    charger_slots={
                        sid: list(s)
                        for sid, s in charger_slots.items()
                    },
                    bus_cumulative_wait=dict(bus_cumulative_wait),
                    operator_total_wait=dict(operator_total_wait),
                    operator_bus_counts=dict(operator_bus_counts),
                    network_total_wait=network_total_wait,
                )

                plan = self._plan_selection_strategy.choose_plan(
                    candidates, bus, scenario, sel_state
                )
                state.plan = plan

                # Record this bus's commitment so later buses can see it
                for sid in plan:
                    station_usage[sid] += 1

                timelines[bus_id].events.append(TimelineEvent(
                    bus_id=bus_id,
                    event_type="DEPARTED",
                    station_id=origin,
                    time_minutes=event.timestamp,
                    notes=f"Full charge. Plan: {' → '.join(plan)}",
                ))

                first_station = plan[0]
                dist = bus_route.distance_between(
                    state.last_position, first_station
                )
                travel = self._travel_strategy.travel_minutes(bus, dist, {})
                arr_t = event.timestamp + travel

                arrival_times[(bus_id, first_station)] = arr_t
                queue.push(StationArrivalEvent(
                    timestamp=arr_t,
                    bus_id=bus_id,
                    station_id=first_station,
                    distance_from_last=dist,
                ))

            # ---- StationArrival ----
            elif isinstance(event, StationArrivalEvent):
                station_id = event.station_id
                t = event.timestamp
                arrival_times[(bus_id, station_id)] = t

                timelines[bus_id].events.append(TimelineEvent(
                    bus_id=bus_id,
                    event_type="ARRIVED",
                    station_id=station_id,
                    time_minutes=t,
                    notes=f"Arrived at {station_id}",
                ))

                slots = charger_slots[station_id]
                earliest_free = min(slots)
                slot_idx = slots.index(earliest_free)

                if earliest_free <= t:
                    self._start_charging(
                        bus, state, station_id, t, 0.0,
                        slots, slot_idx, scenario, queue, timelines,
                    )
                else:
                    waiting_queues[station_id].append(bus_id)
                    timelines[bus_id].events.append(TimelineEvent(
                        bus_id=bus_id,
                        event_type="WAITING",
                        station_id=station_id,
                        time_minutes=t,
                        notes=(
                            "Waiting for charger "
                            f"(free ~{self._fmt(earliest_free)})"
                        ),
                    ))

            # ---- ChargingStarted ----
            elif isinstance(event, ChargingStartedEvent):
                timelines[bus_id].events.append(TimelineEvent(
                    bus_id=bus_id,
                    event_type="CHARGING_STARTED",
                    station_id=event.station_id,
                    time_minutes=event.timestamp,
                    notes=(
                        "Charging started "
                        f"(waited {event.wait_minutes:.0f} min)"
                    ),
                ))

            # ---- ChargingCompleted ----
            elif isinstance(event, ChargingCompletedEvent):
                station_id = event.station_id
                t = event.timestamp

                timelines[bus_id].events.append(TimelineEvent(
                    bus_id=bus_id,
                    event_type="CHARGING_COMPLETED",
                    station_id=station_id,
                    time_minutes=t,
                    notes="Battery full.",
                ))

                station_logs[station_id].charging_order.append(bus_id)
                station_logs[station_id].entries.append({
                    "bus_id": bus_id,
                    "operator": bus.operator,
                    "charge_end": self._fmt(t),
                })

                state.last_position = station_id
                state.last_position_time = t
                state.plan_index += 1

                bus_route = scenario.get_route(bus.route_id)
                destination = bus_route.stops[-1]

                if state.plan_index >= len(state.plan):
                    dist = bus_route.distance_between(
                        station_id, destination
                    )
                    travel = self._travel_strategy.travel_minutes(
                        bus, dist, {}
                    )
                    arr_t = t + travel
                    queue.push(TripCompletedEvent(
                        timestamp=arr_t,
                        bus_id=bus_id,
                        destination=destination,
                        total_wait_minutes=state.cumulative_wait,
                    ))
                    timelines[bus_id].events.append(TimelineEvent(
                        bus_id=bus_id,
                        event_type="EN_ROUTE_FINAL",
                        station_id=None,
                        time_minutes=t,
                        notes=(
                            f"Heading to {destination} "
                            f"(arrives {self._fmt(arr_t)})"
                        ),
                    ))
                else:
                    next_station = state.plan[state.plan_index]
                    dist = bus_route.distance_between(
                        station_id, next_station
                    )
                    travel = self._travel_strategy.travel_minutes(
                        bus, dist, {}
                    )
                    arr_t = t + travel
                    arrival_times[(bus_id, next_station)] = arr_t
                    queue.push(StationArrivalEvent(
                        timestamp=arr_t,
                        bus_id=bus_id,
                        station_id=next_station,
                        distance_from_last=dist,
                    ))

                # Release charger; serve the next waiting bus if any
                if waiting_queues[station_id]:
                    ctx = make_context(t)
                    waiting_buses = [
                        bus_states[bid].bus
                        for bid in waiting_queues[station_id]
                        if bid in bus_states
                    ]
                    ranked = scoring.rank_queue(waiting_buses, ctx)
                    next_bus = ranked[0]
                    waiting_queues[station_id] = [
                        bid for bid in waiting_queues[station_id]
                        if bid != next_bus.id
                    ]

                    arr_t_next = arrival_times.get(
                        (next_bus.id, station_id), t
                    )
                    wait = max(0.0, t - arr_t_next)

                    bus_cumulative_wait[next_bus.id] = (
                        bus_cumulative_wait.get(next_bus.id, 0.0) + wait
                    )
                    operator_total_wait[next_bus.operator] += wait
                    network_total_wait += wait
                    bus_states[next_bus.id].cumulative_wait += wait

                    slots = charger_slots[station_id]
                    min_slot_idx = slots.index(min(slots))
                    self._start_charging(
                        next_bus, bus_states[next_bus.id],
                        station_id, t, wait,
                        slots, min_slot_idx, scenario, queue, timelines,
                    )
                else:
                    slots = charger_slots[station_id]
                    slots[slots.index(min(slots))] = t

            # ---- TripCompleted ----
            elif isinstance(event, TripCompletedEvent):
                timelines[bus_id].final_arrival_minutes = event.timestamp
                timelines[bus_id].total_wait_minutes = (
                    state.cumulative_wait
                )
                timelines[bus_id].completed = True
                timelines[bus_id].events.append(TimelineEvent(
                    bus_id=bus_id,
                    event_type="ARRIVED_DESTINATION",
                    station_id=event.destination,
                    time_minutes=event.timestamp,
                    notes=(
                        f"Arrived at {event.destination}. "
                        f"Total wait: {state.cumulative_wait:.0f} min"
                    ),
                ))

        return ScheduleResult(
            scenario_id=scenario.id,
            bus_timelines=timelines,
            station_logs=station_logs,
            total_network_wait_minutes=sum(bus_cumulative_wait.values()),
        )

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _start_charging(
        self,
        bus: Bus,
        state: BusState,
        station_id: str,
        start_time: float,
        wait: float,
        slots: list[float],
        slot_idx: int,
        scenario: Scenario,
        queue: EventQueue,
        timelines: dict[str, BusTimeline],
    ) -> None:
        """Assign a charger slot; push ChargingStarted + ChargingCompleted."""
        station = scenario.get_station(station_id)
        duration = self._charging_strategy.duration_minutes(bus, station, {})
        charge_end = start_time + duration

        slots[slot_idx] = charge_end

        stop = ChargingStop(
            station_id=station_id,
            planned_arrival_minutes=start_time - wait,
            actual_arrival_minutes=start_time - wait,
            wait_minutes=wait,
            charge_start_minutes=start_time,
            charge_end_minutes=charge_end,
        )
        timelines[bus.id].charging_stops.append(stop)

        bus_route = scenario.get_route(bus.route_id)
        next_plan_idx = state.plan_index + 1
        is_final = next_plan_idx >= len(state.plan)
        next_stop = (
            bus_route.stops[-1] if is_final else state.plan[next_plan_idx]
        )

        queue.push(ChargingStartedEvent(
            timestamp=start_time,
            bus_id=bus.id,
            station_id=station_id,
            wait_minutes=wait,
        ))
        queue.push(ChargingCompletedEvent(
            timestamp=charge_end,
            bus_id=bus.id,
            station_id=station_id,
            next_station_id=next_stop,
            is_final_leg=is_final,
        ))

    @staticmethod
    def _fmt(minutes: float) -> str:
        h = int(minutes // 60) % 24
        m = int(minutes % 60)
        return f"{h:02d}:{m:02d}"
