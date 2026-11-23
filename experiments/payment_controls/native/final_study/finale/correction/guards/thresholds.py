"""Descriptive threshold sensitivity of the frozen risk score for each sampled cohort."""
from collections import Counter
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
POSITIVE = {"REVIEW", "BLOCK", "MUST_STOP_OR_REVIEW"}


def measure(rows):
    points = [(r["jev"]["score"], int(r["gold"]["label"] in POSITIVE)) for r in rows
              if r["jev"]["status"] == "valid" and r["gold"]["label"] in POSITIVE | {"ADMISSIBLE", "ALLOW"}]
    bins = []
    for i in range(10):
        group = [(p, y) for p, y in points if min(9, int(p * 10)) == i]
        if group:
            bins.append({"lower": i/10, "upper": (i+1)/10, "n": len(group), "observed": sum(y for p,y in group),
                         "mean_model_score": sum(p for p,y in group)/len(group)})
    eps = 1e-15
    rates = {}
    for t in (.99, .97, .95, .90, .85, .80, .70, .50):
        counts = Counter((y, p >= t) for p, y in points)
        rates[str(t)] = {"detected": counts[1, True], "missed": counts[1, False],
                         "false_stops": counts[0, True], "correct_allow": counts[0, False]}
    return {"observations": len(points), "risk_positive": sum(y for _,y in points), "bins": bins, "thresholds": rates,
            "brier": sum((p-y)**2 for p,y in points)/len(points),
            "natural_log_loss_clipped_1e_15": -sum(math.log(max(eps, p if y else 1-p)) for p,y in points)/len(points)}


def main():
    data = json.loads((HERE / "primary-results.json").read_bytes())
    result = {name: measure([r for r in data["rows"] if r["source"]+"/"+r["point"] == name])
              for name in ("historical/P1", "modern/P1", "modern/P4")}
    (HERE / "thresholds.json").write_text(json.dumps(result, indent=2)+"\n")


if __name__ == "__main__":
    main()
