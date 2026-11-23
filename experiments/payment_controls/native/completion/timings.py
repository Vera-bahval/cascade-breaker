"""Observed wall times by distinct clock, with interpolated sample quantiles."""
import json
from math import floor
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNTIME = HERE.parents[3] / ".runtime/payment-controls-chp3"


def read(name):
    return json.loads((HERE / (name + ".json")).read_bytes())


def describe(times):
    values = sorted(times)
    assert values and all(x >= 0 for x in values)
    def quantile(q):
        pos = (len(values) - 1) * q
        i = floor(pos)
        return round(values[i] + (pos - i) * (values[min(i+1, len(values)-1)] - values[i]), 3)
    return {"n":len(values), "p50_s":quantile(.50), "p95_s":quantile(.95)}


def assess():
    cohorts = {}
    for label, name, field in (
        ("money_continuation","money_results","live_seconds"),
        ("mail_complete","mail_results","elapsed_seconds"),
        ("onboarding","process_results","wall_seconds"),
        ("chat_reminder","process_chat_results","wall_seconds"),
        ("chat_optional","selector_results","wall_seconds"),
        ("vendor_status","vendor_results","wall_time_seconds"),
    ):
        data = read(name)
        rows = data.get("cells",data.get("rows"))
        if isinstance(rows,dict):
            rows = [{**r, "arm":k.split("--")[-1]} for k,r in rows.items()]
        cohorts[label] = {arm:describe([r[field] for r in rows if r["arm"]==arm]) for arm in sorted({v["arm"] for v in rows})}
    panel=[]
    for path in (RUNTIME / "contrast-v1/receipts").glob("*.json"):
        receipt=json.loads(path.read_bytes())
        if "seconds" in receipt and "request_sha256" in receipt:
            panel.append(receipt["seconds"])
    assert len(panel)==read("contrast_results")["requests"]
    return {"workflow_or_continuation_wall_seconds":cohorts,"jev_client_round_trip_seconds":describe(panel),
            "scope":"Per-method clocks. Small strata: descriptive only. Excludes series without a comparable end-to-end timer; no sum of component quantiles."}


if __name__ == "__main__":
    (HERE/"timings.json").write_text(json.dumps(assess(), indent=2)+"\n")
