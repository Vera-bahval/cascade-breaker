"""Compare ways of reading one frozen Jev answer upstream and downstream, on observed stock prefixes."""
from collections import Counter
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
METHODS = {"До Payments": {"P1": "effective"}, "До FinStripe": {"P4": "effective"},
           "Обе точки, порог 0,97": {"P1": "effective", "P4": "effective"},
           "Обе точки, поздний ответ по максимальной категории": {"P1": "effective", "P4": "choice"}}


def evaluate():
    study = json.loads((HERE / "primary-results.json").read_bytes())
    cases = json.loads((HERE.parents[1] / "review/assignment_outcomes.json").read_bytes())
    records = {r["assignment"]: [] for r in cases if (r["kind"], r["arm"]) == ("main", "A")}
    pre_calls = {}
    for r in study["rows"]:
        if r["source"] == "modern":
            assert r["jev"]["status"] == "valid"
            records[r["assignment"]].append(r)
    assert len(records) == 221 and sum(map(len, records.values())) == 391
    for name, modes in METHODS.items():
        f = Counter()
        cases_with_issue = set()
        seen = set()
        fees = 0
        for assignment, rows in records.items():
            first = False
            for r in sorted(rows, key=lambda x:x["capture"]):
                if r["point"] not in modes:
                    continue
                label = r["gold"]["label"]
                if label == "MUST_STOP_OR_REVIEW":
                    cases_with_issue.add(assignment)
                if first:
                    continue
                seen.add(assignment)
                mode = modes[r["point"]]
                f["consultations"] += 1
                fees += r["jev"]["cost_usd"]
                if r["jev"][mode] != "ALLOW":
                    first = True
                    f["justified_first_stops" if label=="MUST_STOP_OR_REVIEW" else "false_first_stops"] += 1
        pre_calls[name] = {"assigned": len(records), "families_reached": len(seen),
                           "families_with_observed_problem_at_chosen_points": len(cases_with_issue),
                           "first_justified": f["justified_first_stops"], "first_false": f["false_first_stops"],
                           "evaluated_actions": f["consultations"], "sum_guard_only_receipt_usd": fees}
    return pre_calls


if __name__ == '__main__':
    (HERE / "joint_replay.json").write_text(json.dumps(evaluate(),ensure_ascii=False,indent=2)+"\n")
