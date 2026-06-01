# SmartCharge Scheduler — Architecture

## Requirements

### Functional Requirements
1. **Scenario Management**: Load and execute predefined scheduling scenarios containing buses, routes, stations, and optimization weights.
2. **Charging Plan Generation**: Generate feasible charging plans for buses while satisfying battery and route constraints.
3. **Schedule Optimization**: Select charging plans and charger allocations that optimize individual, operator, and overall network objectives.
4. **Event-Driven Simulation**: Simulate bus journeys, charging events, waiting times, and trip completion chronologically.
5. **Resource Allocation**: Manage charger availability and resolve conflicts when multiple buses compete for charging stations.
6. **Schedule Visualization**: Display scenario inputs, bus timelines, and station-wise charging schedules.
7. **Extensible Scheduling Framework**: Support future addition of routes, stations, chargers, operators, constraints, and optimization rules with minimal code changes.

### Non-Functional Requirements
1. **Scalability**: Scheduler should be scalable with load and features.
2. **Maintainability**: Scheduler should be easy to maintain and modify.

### Real-World Challenges & Future Possibilities
1. **Variable Bus Speeds**: Buses may not have fixed travel speeds.
2. **Distinct Directional Paths**: The routes from A → B and B → A are different and should not be treated as a single path.
3. **Shared Stations across Multiple Routes**: Stations like C can be part of different overlapping paths and serve different destinations in the future.
4. **Dynamic Charging Duration**: Charging times can be dynamic rather than fixed.
5. **Active Running States**: Some vehicles may already be running when planning starts, making their initial active state important.
6. **Varying Charging Capacities**: All buses may not have a fixed charging or battery capacity.
7. **Varying Station Charging Slots**: Different stations may have different numbers of charging slots available.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Streamlit UI                            │
└──────────────────────────────┬──────────────────────────────────┘
                               │ Scenario + Weights
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                       SchedulerEngine                           │
│                                                                 │
│   Phase 1 — Seed departure events (plans deferred)              │
│   Phase 2 — Process event queue chronologically                 │
│                                                                 │
│   ┌──────────────────┐     ┌──────────────────────────────┐     │
│   │  PlanGenerator   │     │     EventQueue (min-heap)    │     │
│   │                  │     │                              │     │
│   │ generate_valid_  │     │  BusDepartureEvent           │     │
│   │ plans()          │     │  StationArrivalEvent         │     │
│   │                  │     │  ChargingStartedEvent        │     │
│   │ Constraints:     │     │  ChargingCompletedEvent      │     │
│   │  BatteryConstraint     │  TripCompletedEvent          │     │
│   │  RouteConstraint │     └──────────────────────────────┘     │
│   │  ChargerConstraint                                          │
│   └──────────────────┘                                          │
│                                                                 │
│   ┌──────────────────────────┐  ┌─────────────────────────┐     │
│   │  PlanSelectionStrategy   │  │    ScoringStrategy      │     │
│   │                          │  │                         │     │
│   │  FewestStopsStrategy     │  │  IndividualWaitRule     │     │
│   │  LoadBalancedStrategy    │  │  OperatorFairnessRule   │     │
│   │  WeightedScoringStrategy │  │  OverallDelayRule       │     │
│   └──────────────────────────┘  └─────────────────────────┘     │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
                       ScheduleResult
               (bus timelines, station logs, KPIs)
```


## Component Responsibilities

### PlanGenerator
- **Does**: enumerates every subset of stations in route order; filters by constraints
- **Does not**: decide which plan is best; access simulation state; know about scoring

### PlanSelectionStrategy *(new)*
- **Does**: picks one plan from the feasible set, given a snapshot of scheduler state at departure time
- **Does not**: modify simulation state; interact with the event queue

### SchedulerEngine
- **Does**: owns the event queue and all mutable simulation state; wires components together
- **Does not**: implement any routing logic, scoring logic, or constraint logic directly

### ScoringStrategy
- **Does**: aggregates weighted rule penalties to rank buses competing for a charger
- **Does not**: influence route planning; know which charger is contested

### Constraints (hard rules)
- **Accept or reject** a candidate plan before simulation starts
- Stateless — they see only the plan and the scenario, never runtime state

### Scoring Rules (soft rules)
- **Penalise** a bus during conflict resolution at a specific charger
- Stateless — they see only the bus and a `SimulationContext` snapshot

---

## Extension Points

| What to add | Where | Engine changes? |
|---|---|---|
| New hard constraint | Subclass `Constraint`, register in `SchedulerEngine.__init__` | No |
| New scoring rule | Subclass `ScoringRule`, register in `ScoringStrategy.__init__` | No |
| New plan selection algorithm | Subclass `PlanSelectionStrategy` | No |
| Dynamic charging duration | Subclass `ChargingStrategy` | No |
| Traffic-aware travel time | Subclass `TravelTimeStrategy` | No |

---

## Plan Selection Strategy Comparison

| Strategy | Input used | Unique plans (20-bus scenario) | Best for |
|---|---|---|---|
| `FewestStopsStrategy` | none (ignores state) | 2 (one per direction) | baseline / debugging |
| `LoadBalancedStrategy` | `station_usage` | 2–4 | general use; reduces artificial congestion |
| `WeightedScoringStrategy` | `station_usage` + `waiting_queues` + `charger_slots` | 4+ | operator-tuned scenarios with uneven load |

**Default**: `LoadBalancedStrategy` — it eliminates the core flaw (all buses picking the same path) with minimal complexity.

---

## Algorithm Decisions

### Why plans are selected at departure time, not upfront

| Timing | Problem |
|---|---|
| **Upfront (Phase 1)** | All buses see empty state → `station_usage = {}` for all → strategy cannot differentiate → same plan wins every time |
| **At departure (chosen)** | Bus departing at 07:30 sees all commitments from buses departing at 06:00–07:00. `station_usage` reflects real network load → genuine diversification |
| **At each station** | True dynamic replanning — but breaks the "plan as a unit" model and requires significant engine changes. Out of scope for this assignment. |

### Why `station_usage` is cumulative, not real-time

`station_usage[s]` counts every bus committed to charge at station `s`, not just buses currently present. A bus committed to arrive at station A at 09:00 should influence the plan of a bus departing at 06:00, even though A is currently empty. Real-time queue length (`waiting_queues`) is also exposed for strategies that want finer resolution.
