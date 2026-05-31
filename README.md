# SmartCharge — Electric Bus Fleet Charging Scheduler

An event-driven simulation engine for scheduling electric bus charging stops across a multi-station highway corridor. Built with Python and Streamlit.

---

## What it does

Given a fleet of buses, a set of charging stations, and a route, SmartCharge:

1. **Generates all feasible charging plans** for each bus — ordered lists of stations that satisfy battery range, route order, and charger availability constraints
2. **Selects a plan** for each bus at departure time using a pluggable strategy that accounts for real network load (station commitments, queue depths, charger availability)
3. **Simulates the full trip** event-by-event — arrivals, waits, charges, and departures — resolving charger contention using weighted fairness rules
4. **Reports results** as per-bus timelines, per-station logs, and fleet-wide KPIs

---

## Quick start

### Local (Python 3.11+)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run src/app.py
```

### Docker

```bash
docker compose up --build
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Project structure

```
src/
├── app.py                          # Streamlit entry point
├── domain/
│   ├── models.py                   # Pydantic data models
│   └── enums.py                    # EventType, BusStatus
├── scheduler/
│   ├── engine.py                   # Event-driven simulation engine
│   ├── plan_generator.py           # Feasibility filter (generates candidate plans)
│   ├── events/                     # Event dataclasses + min-heap queue
│   ├── constraints/                # Hard constraints (battery, route, charger)
│   ├── strategies/
│   │   ├── plan_selection_strategy.py  # Plan routing strategies (NEW)
│   │   ├── scoring_strategy.py         # Charger contention resolver
│   │   ├── charging_strategy.py        # Charging duration model
│   │   └── travel_time_strategy.py     # Travel time model
│   └── rules/                      # Soft scoring rules (wait fairness, operator, network)
├── services/
│   └── scenario_loader.py          # JSON scenario loader
├── ui/                             # Streamlit UI components
└── scenarios/                      # Five test scenarios (JSON)
```

---

## Scenarios

| ID | Name | What it tests |
|----|------|---------------|
| scenario1 | Even Spacing | Baseline — buses depart at regular intervals |
| scenario2 | Peak Hour Clustering | Multiple buses competing for chargers simultaneously |
| scenario3 | Asymmetric Load | Imbalanced load between the two directions |
| scenario4 | Operator Dominance | One operator has significantly more buses |
| scenario5 | Worst-Case Convergence | Maximum contention across all stations |

---

## Plan selection strategies

The strategy is injected into `SchedulerEngine` and chosen at bus departure time so each bus sees real network load:

| Strategy | How it picks a plan | Best for |
|---|---|---|
| `FewestStopsStrategy` | Shortest plan (fewest charges) | Baseline / debugging |
| `LoadBalancedStrategy` | Lowest total committed load across stops | General use — reduces artificial congestion |
| `WeightedScoringStrategy` | Composite score: committed load + queue depth + expected wait, weighted by scenario sliders | Operator-tuned uneven scenarios |

Default: `LoadBalancedStrategy`.

To use a different strategy:

```python
from src.scheduler.engine import SchedulerEngine
from src.scheduler.strategies import WeightedScoringStrategy

engine = SchedulerEngine(plan_selection_strategy=WeightedScoringStrategy())
result = engine.run(scenario)
```

---

## Charger conflict resolution

When multiple buses compete for a charger, they are ranked by a composite score:

```
score(bus) = individual_weight × IndividualWaitRule.penalty(bus)
           + operator_weight   × OperatorFairnessRule.penalty(bus)
           + overall_weight    × OverallDelayRule.penalty(bus)
```

Lower score = higher priority. Weights are tuned per scenario via the sidebar sliders.

---

## Adding a new plan selection strategy

1. Create a subclass of `PlanSelectionStrategy` in `src/scheduler/strategies/plan_selection_strategy.py`
2. Implement `choose_plan(candidate_plans, bus, scenario, scheduler_state) -> list[str]`
3. Pass an instance to `SchedulerEngine(plan_selection_strategy=YourStrategy())`

No changes to the engine, constraints, or rules required.

---

## Adding a new scoring rule

1. Create a subclass of `ScoringRule` in `src/scheduler/rules/`
2. Implement `name` and `penalty(bus, context) -> float`
3. Register it in `ScoringStrategy.__init__` with its weight accessor

---

## Running tests

```bash
pytest
```
