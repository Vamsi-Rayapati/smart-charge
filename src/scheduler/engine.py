"""
SchedulerEngine — Core event-driven simulation engine.

Algorithm:
  Phase 1 — Plan Generation:
    For each bus, enumerate all valid charging plans (via PlanGenerator + Constraints).
    Select the best plan (fewest stops, earliest stations).

  Phase 2 — Event-Driven Simulation:
    Push BusDeparture events for all buses.
    Process events chronologically from min-heap priority queue:

    BusDeparture     → compute travel time to first charging station
                       → push StationArrival
    StationArrival   → if charger available: immediately start charging
                       → else: add bus to waiting queue (sorted by score)
    ChargingStarted  → record in timeline
    ChargingCompleted→ release charger slot
                       → serve next waiting bus (scored by rules)
                       → push next event for this bus (next station or destination)
    TripCompleted    → record final arrival

  Charger State:
    charger_slots[station_id]: list of floats (free-at timestamps), one per charger.
    Supports num_chargers > 1 transparently — no code change needed.

  Conflict Resolution:
    When charger is busy, bus enters waiting_queue[station_id].
    When charger frees up, all waiting buses are scored and the lowest-score
    bus wins (ScoringStrategy.rank_queue).
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field

from src.domain.models import (
    Scenario, Bus, BusTimeline, StationLog,
    ScheduleResult, ChargingStop, TimelineEvent
)
from src.scheduler.events.event import (
    BusDepartureEvent, StationArrivalEvent,
    ChargingStartedEvent, ChargingCompletedEvent, TripCompletedEvent
)
from src.scheduler.events.event_queue import EventQueue
from src.scheduler.rules.base_rule import SimulationContext
from src.scheduler.strategies.charging_strategy import ChargingStrategy, FixedChargingStrategy
from src.scheduler.strategies.travel_time_strategy import TravelTimeStrategy, FixedSpeedStrategy
from src.scheduler.strategies.scoring_strategy import ScoringStrategy
from src.scheduler.constraints.battery_constraint import BatteryConstraint
from src.scheduler.constraints.charger_constraint import ChargerCapacityConstraint
from src.scheduler.constraints.route_constraint import RouteOrderConstraint
from src.scheduler.plan_generator import PlanGenerator


@dataclass
class BusState:
    """All mutable runtime state for a single bus during simulation."""
    bus: Bus
    plan: list[str]                  # Ordered charging station IDs
    plan_index: int = 0              # Index into plan (which stop we just reached)
    cumulative_wait: float = 0.0     # Total minutes waited so far
    last_position: str = ""          # Last position (station or origin)
    last_position_time: float = 0.0  # Time we left last position


class SchedulerEngine:
    """
    Event-driven bus charging scheduler.

    Wires together PlanGenerator, EventQueue, ScoringStrategy,
    ChargingStrategy, and TravelTimeStrategy.

    Adding rules, constraints, or strategies never requires modifying this file.
    """

    def __init__(
        self,
        charging_strategy: ChargingStrategy | None = None,
        travel_time_strategy: TravelTimeStrategy | None = None,
    ) -> None:
        self._charging_strategy = charging_strategy or FixedChargingStrategy()
        self._travel_strategy = travel_time_strategy or FixedSpeedStrategy()
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

        # Charger slots: station_id → list[float] (one free-at per charger)
        charger_slots: dict[str, list[float]] = {
            s.id: [0.0] * s.num_chargers for s in scenario.stations
        }

        # Waiting queues: station_id → list of bus_ids in arrival order
        waiting_queues: dict[str, list[str]] = defaultdict(list)

        # Arrival times at each station (for wait calculation)
        arrival_times: dict[tuple[str, str], float] = {}  # (bus_id, station_id) → time

        # Cumulative wait tracking (for scoring rules)
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

        # --- Phase 1: Generate plans and seed events ---
        for bus in scenario.buses:
            if bus.status.value == "CANCELLED":
                continue

            bus_route = scenario.get_route(bus.route_id)
            plan = self._plan_generator.best_plan(bus, bus_route, scenario)
            origin = bus_route.stops[0]

            bus_states[bus.id] = BusState(
                bus=bus,
                plan=plan,
                last_position=origin,
                last_position_time=bus.departure_minutes(),
            )
            timelines[bus.id] = BusTimeline(bus=bus)

            # Seed the queue with departure events
            queue.push(BusDepartureEvent(
                timestamp=bus.departure_minutes(),
                bus_id=bus.id,
                next_station_id=plan[0] if plan else origin,
            ))

            timelines[bus.id].events.append(TimelineEvent(
                bus_id=bus.id,
                event_type="DEPARTED",
                station_id=origin,
                time_minutes=bus.departure_minutes(),
                notes=f"Full charge. Plan: {' → '.join(plan)}",
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
                    station_queue_length={sid: len(q) for sid, q in waiting_queues.items()},
                )

            # ---- BusDeparture ----
            if isinstance(event, BusDepartureEvent):
                first_station = state.plan[0]
                bus_route = scenario.get_route(bus.route_id)
                dist = bus_route.distance_between(state.last_position, first_station)
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
                    bus_id=bus_id, event_type="ARRIVED",
                    station_id=station_id, time_minutes=t,
                    notes=f"Arrived at {station_id}",
                ))

                # Find earliest free charger slot
                slots = charger_slots[station_id]
                earliest_free = min(slots)
                slot_idx = slots.index(earliest_free)

                if earliest_free <= t:
                    # Charger free — start immediately, no wait
                    self._start_charging(
                        bus, state, station_id, t, 0.0,
                        slots, slot_idx, scenario, queue,
                        timelines, bus_cumulative_wait,
                        operator_total_wait,
                    )
                    nonlocal_wait = 0.0
                    network_total_wait += nonlocal_wait
                else:
                    # Must wait — add to queue
                    waiting_queues[station_id].append(bus_id)
                    timelines[bus_id].events.append(TimelineEvent(
                        bus_id=bus_id, event_type="WAITING",
                        station_id=station_id, time_minutes=t,
                        notes=f"Waiting for charger (free ~{self._fmt(earliest_free)})",
                    ))

            # ---- ChargingStarted ----
            elif isinstance(event, ChargingStartedEvent):
                timelines[bus_id].events.append(TimelineEvent(
                    bus_id=bus_id, event_type="CHARGING_STARTED",
                    station_id=event.station_id, time_minutes=event.timestamp,
                    notes=f"Charging started (waited {event.wait_minutes:.0f} min)",
                ))

            # ---- ChargingCompleted ----
            elif isinstance(event, ChargingCompletedEvent):
                station_id = event.station_id
                t = event.timestamp

                timelines[bus_id].events.append(TimelineEvent(
                    bus_id=bus_id, event_type="CHARGING_COMPLETED",
                    station_id=station_id, time_minutes=t,
                    notes="Battery full.",
                ))

                # Log in station log
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
                    # Head to destination
                    dist = bus_route.distance_between(station_id, destination)
                    travel = self._travel_strategy.travel_minutes(bus, dist, {})
                    arr_t = t + travel
                    queue.push(TripCompletedEvent(
                        timestamp=arr_t,
                        bus_id=bus_id,
                        destination=destination,
                        total_wait_minutes=state.cumulative_wait,
                    ))
                    timelines[bus_id].events.append(TimelineEvent(
                        bus_id=bus_id, event_type="EN_ROUTE_FINAL",
                        station_id=None, time_minutes=t,
                        notes=f"Heading to {destination} (arrives {self._fmt(arr_t)})",
                    ))
                else:
                    # Head to next charging station
                    next_station = state.plan[state.plan_index]
                    dist = bus_route.distance_between(station_id, next_station)
                    travel = self._travel_strategy.travel_minutes(bus, dist, {})
                    arr_t = t + travel
                    arrival_times[(bus_id, next_station)] = arr_t
                    queue.push(StationArrivalEvent(
                        timestamp=arr_t,
                        bus_id=bus_id,
                        station_id=next_station,
                        distance_from_last=dist,
                    ))

                # Release charger and serve next waiting bus
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

                    # Compute wait time
                    arr_t_next = arrival_times.get((next_bus.id, station_id), t)
                    wait = max(0.0, t - arr_t_next)

                    # Update wait tracking
                    bus_cumulative_wait[next_bus.id] = (
                        bus_cumulative_wait.get(next_bus.id, 0.0) + wait
                    )
                    operator_total_wait[next_bus.operator] += wait
                    network_total_wait += wait
                    bus_states[next_bus.id].cumulative_wait += wait

                    # Find a free slot (the one we just finished with)
                    slots = charger_slots[station_id]
                    min_slot_idx = slots.index(min(slots))

                    self._start_charging(
                        next_bus, bus_states[next_bus.id], station_id, t, wait,
                        slots, min_slot_idx, scenario, queue,
                        timelines, bus_cumulative_wait,
                        operator_total_wait,
                    )
                    network_total_wait += 0  # wait already counted above
                else:
                    # Free the charger: reset the earliest slot to now
                    slots = charger_slots[station_id]
                    min_idx = slots.index(min(slots))
                    slots[min_idx] = t

            # ---- TripCompleted ----
            elif isinstance(event, TripCompletedEvent):
                timelines[bus_id].final_arrival_minutes = event.timestamp
                timelines[bus_id].total_wait_minutes = state.cumulative_wait
                timelines[bus_id].completed = True
                timelines[bus_id].events.append(TimelineEvent(
                    bus_id=bus_id, event_type="ARRIVED_DESTINATION",
                    station_id=event.destination, time_minutes=event.timestamp,
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
        bus_cumulative_wait: dict[str, float],
        operator_total_wait: dict[str, float],
    ) -> None:
        """Assign a charger slot and push ChargingStarted + ChargingCompleted events."""
        station = scenario.get_station(station_id)
        duration = self._charging_strategy.duration_minutes(bus, station, {})
        charge_end = start_time + duration

        # Reserve the slot
        slots[slot_idx] = charge_end

        # Record charging stop
        stop = ChargingStop(
            station_id=station_id,
            planned_arrival_minutes=start_time - wait,
            actual_arrival_minutes=start_time - wait,
            wait_minutes=wait,
            charge_start_minutes=start_time,
            charge_end_minutes=charge_end,
        )
        timelines[bus.id].charging_stops.append(stop)

        # Determine if this is the bus's last charging stop
        bus_route = scenario.get_route(bus.route_id)
        next_plan_idx = state.plan_index + 1  # After this charge
        is_final = next_plan_idx >= len(state.plan)

        next_stop = (
            bus_route.stops[-1]
            if is_final
            else state.plan[next_plan_idx]
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
