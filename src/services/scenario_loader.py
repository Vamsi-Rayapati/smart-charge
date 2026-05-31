"""
ScenarioLoader — Loads and validates scenario JSON files.

Scenarios are fully self-contained JSON documents. This service:
1. Discovers all scenario files in the scenarios/ directory
2. Parses them into validated Pydantic Scenario objects
3. Provides a registry of available scenarios for the UI dropdown

Adding a new scenario: drop a new .json file in scenarios/ — no code changes.
"""
from __future__ import annotations
import json
from pathlib import Path

from src.domain.models import Scenario


SCENARIOS_DIR = Path(__file__).parent.parent / "scenarios"


class ScenarioLoader:
    """
    Loads scenario JSON files and returns validated Scenario models.
    
    Discovery is automatic: any .json file in the scenarios/ directory
    is treated as a scenario. Files are sorted by filename for stable ordering.
    """

    def __init__(self, scenarios_dir: Path | None = None) -> None:
        self._dir = scenarios_dir or SCENARIOS_DIR

    def load_all(self) -> dict[str, Scenario]:
        """
        Load all scenario files. Returns dict: scenario_id → Scenario.
        Sorted by scenario ID for consistent dropdown ordering.
        """
        scenarios: dict[str, Scenario] = {}
        if not self._dir.exists():
            return scenarios

        for path in sorted(self._dir.glob("*.json")):
            try:
                scenario = self.load_file(path)
                scenarios[scenario.id] = scenario
            except Exception as e:
                # Log but don't crash — let the UI show available scenarios
                print(f"Warning: Failed to load {path.name}: {e}")

        return scenarios

    def load_file(self, path: Path) -> Scenario:
        """Load and validate a single scenario file."""
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return Scenario.model_validate(data)

    def load_by_id(self, scenario_id: str) -> Scenario:
        """Load a specific scenario by its ID (looks for <id>.json)."""
        path = self._dir / f"{scenario_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Scenario file not found: {path}")
        return self.load_file(path)

    def available_scenarios(self) -> list[tuple[str, str]]:
        """
        Return list of (scenario_id, scenario_name) tuples for the UI dropdown.
        """
        scenarios = self.load_all()
        return [(sid, s.name) for sid, s in scenarios.items()]
