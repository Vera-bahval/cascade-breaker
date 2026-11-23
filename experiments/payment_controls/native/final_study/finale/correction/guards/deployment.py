"""Cost per request and timed receipt quantiles for each ready-made guard and checkpoint."""
from math import ceil
from statistics import median
from pathlib import Path
import json

HERE = Path(__file__).resolve().parent


def main():
    rows = json.loads((HERE/"primary-results.json").read_bytes())["rows"]
    stats = {}
    for source, point in (("historical","P1"),("modern","P1"),("modern","P4")):
        selected = [r for r in rows if (r["source"],r["point"]) == (source,point)]
        group = {}
        for arm in ("jev","native_source"):
            data = [r[arm] for r in selected]
            elapsed = sorted(v["seconds"] for v in data)
            prices = [v["cost_usd"] for v in data]
            group[arm] = {"n":len(data), "mean_usd":sum(prices)/len(prices), "sum_usd":sum(prices),
                          "median_seconds":median(elapsed), "nearest_rank_p95_seconds":elapsed[ceil(.95*len(elapsed))-1]}
        stats[source+"/"+point] = group
    (HERE/"deployment-cost.json").write_text(json.dumps(stats,indent=2)+"\n")


if __name__=="__main__":
    main()
