"""Files that connect the prepare step with the run step."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
RESULTS_DIR = ROOT / "results"


def state_path(scenario_id: str) -> Path:
    return STATE_DIR / f"{scenario_id}.json"


def save_state(scenario_id: str, data: dict[str, Any]) -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    path = state_path(scenario_id)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def load_state(scenario_id: str) -> dict[str, Any]:
    path = state_path(scenario_id)
    if not path.exists():
        raise FileNotFoundError(
            f"No prepared state for {scenario_id}; run `prepare {scenario_id}` first"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def save_result(scenario_id: str, data: dict[str, Any]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS_DIR / f"{scenario_id}-{stamp}.json"
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    return path
