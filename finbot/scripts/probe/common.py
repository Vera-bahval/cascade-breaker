"""Shared helpers for probe runner scripts (paths, budget, provenance)."""

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from finbot.config import settings

FINBOT_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_DIR = FINBOT_ROOT.parent.parent / "experiments" / "finbot-probe"
SPEND_LOG = EXPERIMENT_DIR / "spend.jsonl"
BUDGET_USD = 15.0
STOP_FRACTION = 0.8


def git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=FINBOT_ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()


def git_dirty() -> bool:
    out = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=FINBOT_ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return bool(out.strip())


def key_usage() -> dict[str, Any]:
    """Spend and limit of the OpenRouter key, as reported by OpenRouter."""
    base = (settings.OPENAI_BASE_URL or "https://openrouter.ai/api/v1").rstrip("/")
    resp = httpx.get(
        f"{base}/key",
        headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    return {k: data.get(k) for k in ("limit", "usage", "limit_remaining")}


def logged_spend() -> float:
    if not SPEND_LOG.exists():
        return 0.0
    with SPEND_LOG.open(encoding="utf-8") as f:
        return sum(json.loads(line)["cost_usd"] for line in f if line.strip())


def append_spend(label: str, cost_usd: float, **extra: Any) -> None:
    SPEND_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now(UTC).isoformat(),
        "label": label,
        "cost_usd": cost_usd,
        "git_sha": git_sha(),
        **extra,
    }
    with SPEND_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def check_budget(forecast_usd: float) -> None:
    """Print the forecast and refuse to start past 80% of the pilot budget."""
    usage = key_usage()
    spent = max(float(usage["usage"] or 0), logged_spend())
    limit = BUDGET_USD * STOP_FRACTION
    print(
        f"Budget: spent ${spent:.4f} (key ${usage['usage']}, log ${logged_spend():.4f}), "
        f"forecast +${forecast_usd:.4f}, stop line ${limit:.2f}"
    )
    if spent + forecast_usd > limit:
        raise SystemExit("Forecast crosses 80% of the pilot budget; stopping.")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
