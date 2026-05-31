# SmartCharge Scheduler — Architecture

## Requirements

### Functional Requirements

**FR-1 Route feasibility**
Every bus must charge enough times that no single leg of its journey exceeds the bus's battery range. Plans that violate this are rejected before the simulation starts.

**FR-2 Route ordering**
A bus may only stop at stations that appear in order along its route. Backtracking is not permitted.

**FR-3 Station existence**
A bus may only plan to stop at stations that exist in the scenario and have at least one charger.

**FR-4 Charger capacity**
A station with N chargers can serve at most N buses simultaneously. Additional arrivals wait in a queue.

**FR-5 Conflict resolution**
When a charger becomes free and multiple buses are waiting, the bus with the lowest composite score is served first. The score is computed from three weighted rules: individual wait fairness, operator-level fairness, and network-wide delay.

**FR-6 Load-balanced routing**
Plan selection must account for current network state (station commitments, queue depths, charger availability) so that buses are not all routed to the same stations.

**FR-7 Extensibility**
Adding a new constraint, scoring rule, charging duration model, or plan selection strategy must not require changes to the core simulation engine.

**FR-8 Scenario-driven configuration**
All parameters — route topology, fleet composition, station charger counts, and scoring weights — are loaded from JSON scenario files. No hard-coded values in engine code.

**FR-9 Reproducibility**
Given the same scenario file, the simulation must produce identical output on every run (no randomness).

### Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | Simulation of 20 buses across a 5-stop route completes in under 1 second |
| NFR-2 | All components are unit-testable in isolation (strategies, rules, constraints) |
| NFR-3 | A new `PlanSelectionStrategy` can be added by implementing one method; zero engine changes |
| NFR-4 | A new `ScoringRule` can be added by implementing one method and registering it in `ScoringStrategy` |

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Streamlit UI                            │
│   sidebar.py          scenario_tab.py   results_tab.py          │
│   (scenario picker,   (routes, fleet,   (KPIs, timeline,        │
│    weight sliders)     stations)         station logs)           │
└──────────────────────────────┬──────────────────────────────────┘
                               │ Scenario + Weights
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                       SchedulerEngine                           │
│                                                                 │
│   Phase 1 — Seed departure events (plans deferred)             │
│   Phase 2 — Process event queue chronologically                 │
│                                                                 │
│   ┌──────────────────┐     ┌──────────────────────────────┐    │
│   │  PlanGenerator   │     │     EventQueue (min-heap)    │    │
│   │                  │     │                              │    │
│   │ generate_valid_  │     │  BusDepartureEvent           │    │
│   │ plans()          │     │  StationArrivalEvent         │    │
│   │                  │     │  ChargingStartedEvent        │    │
│   │ Constraints:     │     │  ChargingCompletedEvent      │    │
│   │  BatteryConstraint     │  TripCompletedEvent          │    │
│   │  RouteConstraint │     └──────────────────────────────┘    │
│   │  ChargerConstraint                                          │
│   └──────────────────┘                                          │
│                                                                 │
│   ┌──────────────────────────┐  ┌─────────────────────────┐   │
│   │  PlanSelectionStrategy   │  │    ScoringStrategy      │   │
│   │                          │  │                         │   │
│   │  FewestStopsStrategy     │  │  IndividualWaitRule     │   │
│   │  LoadBalancedStrategy    │  │  OperatorFairnessRule   │   │
│   │  WeightedScoringStrategy │  │  OverallDelayRule       │   │
│   └──────────────────────────┘  └─────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                               │
                               ▼
                       ScheduleResult
               (bus timelines, station logs, KPIs)
```

---

## Data Flow

### Plan Generation and Selection

```
Scenario JSON
     │
     ▼
ScenarioLoader ──► Scenario (routes, stations, buses, weights)
     │
     ▼
SchedulerEngine.run()
     │
     ├─ Phase 1: for each bus
     │     └─ push BusDepartureEvent(timestamp=departure_time)
     │
     └─ Phase 2: event loop
           │
           ▼ [BusDepartureEvent fires for bus B at time T]
           │
           ├─ PlanGenerator.generate_valid_plans(bus, route, scenario)
           │       │
           │       ├─ enumerate all station subsets in route order
           │       └─ filter by: BatteryConstraint
           │                     RouteOrderConstraint
           │                     ChargerCapacityConstraint
           │                     ──────────────────────────►  candidate_plans
           │
           ├─ build SchedulerState snapshot (station_usage, queues,
           │         charger_slots, wait totals — all as of time T)
           │
           ├─ PlanSelectionStrategy.choose_plan(candidates, bus,
           │         scenario, scheduler_state)
           │                     ──────────────────────────►  selected_plan
           │
           ├─ station_usage[s] += 1 for each s in selected_plan
           │         (so later buses can see this commitment)
           │
           └─ push StationArrivalEvent for plan[0]
```

### Event-Driven Simulation Loop

```
EventQueue (min-heap, ordered by timestamp)
     │
     ▼
┌────────────────────────────────────────────────────────────────┐
│  pop event                                                     │
│                                                                │
│  BusDeparture ──► select plan (lazy) ──► StationArrival       │
│                                                                │
│  StationArrival                                                │
│    ├─ charger free? ──► _start_charging()                      │
│    │                         └─► ChargingStarted              │
│    │                         └─► ChargingCompleted            │
│    └─ charger busy? ──► waiting_queue[station].append(bus)    │
│                                                                │
│  ChargingCompleted                                             │
│    ├─ update station log                                       │
│    ├─ more stops in plan? ──► StationArrival (next stop)      │
│    ├─ last stop?          ──► TripCompleted                    │
│    └─ waiting_queue not empty?                                 │
│          ├─ ScoringStrategy.rank_queue(waiting_buses, ctx)    │
│          └─ _start_charging(next_bus)                         │
│                                                                │
│  TripCompleted ──► record final arrival + total wait           │
└────────────────────────────────────────────────────────────────┘
```

### Charger Conflict Resolution

```
Bus X completes charging at station S (time = T)
          │
          ▼
    waiting_queue[S] not empty?
          │ yes
          ▼
    build SimulationContext(T, bus_waits, operator_waits, queues)
          │
          ▼
    ScoringStrategy.rank_queue(waiting_buses, context)
          │
          │  score(bus) = Σ weight_i × rule_i.penalty(bus, ctx)
          │
          │  IndividualWaitRule:   penalty = -(bus cumulative wait)
          │  OperatorFairnessRule: penalty = -(operator avg wait)
          │  OverallDelayRule:     penalty = -(network total wait)
          │
          ▼
    serve bus with lowest score (most disadvantaged first)
```

---

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
