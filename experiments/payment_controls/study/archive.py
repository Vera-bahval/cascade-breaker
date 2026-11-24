"""Re-run the frozen payment rule on its original common observation and audit all rows."""
import csv
from collections import Counter
from pathlib import Path

from experiments.local_guards_completion.records import rows
from experiments.local_guards_archive_comparison.collector import digest
from experiments.local_guards_completion.run import admitted
from experiments.local_guards_completion.rules import guard

HERE = Path(__file__).resolve().parent
EXP = HERE.parents[1]
SRC = EXP / "local_guards_completion"


def index(records):
    result = {}
    for row in records:
        pid = row["prefix_id"]
        if pid in result:
            raise ValueError(f"Duplicate prefix {pid}")
        result[pid] = row
    if len(result) != 542:
        raise ValueError("Wrong archive cohort")
    return result


def audit():
    admitted()
    frozen = index(r for r in rows(SRC / "results/predictions.jsonl.gz")
                   if (r["dataset"], r["mode"], r["method"]) == ("p4", "common", "current"))
    labels = index(rows(SRC / "labels.jsonl"))
    ml = index(r for r in rows(SRC / "ml-results/predictions.jsonl.gz") if r["method"] == "catboost")
    llm = index(rows(EXP / "local_guards_repaired_evaluation/results/saved-deepseek.jsonl.gz"))
    for row in rows(SRC / "records.jsonl.gz"):
        pid = row["prefix_id"]
        observation = row["observation"]
        assert digest(observation) == frozen[pid]["input_sha256"]
        before = guard(observation)
        assert before == frozen[pid]["result"]
        # In the updated FinStripe path tax is checked inside the tool before commit.
        facts = {**observation["facts"], "tax_applicable": False}
        after = guard({**observation, "facts": facts})
        label = labels[pid]
        requirements = {**label["core_requirements"], **label["requirements"]}
        yield dict(prefix=pid, substantive=label["substantive_label"], procedure=label["process_label"],
                   recorded_violations="|".join(k for k,v in requirements.items() if v["status"]=="violated"),
                   original=before["decision"], reasons="|".join(before["reasons"]),
                   unknown="|".join(before["unknown_requirements"]), delegated_tax=after["decision"],
                   revised_reasons="|".join(after["reasons"]), catboost=ml[pid]["decision"], deepseek=llm[pid]["decision"])


if __name__ == "__main__":
    data = list(audit())
    assert len({r["prefix"] for r in data}) == len(data) == 542
    with (HERE / "archive_decisions.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=data[0])
        writer.writeheader()
        writer.writerows(data)
    for key in ("original","delegated_tax","catboost","deepseek"):
        print(key,Counter(r[key] for r in data if r["substantive"]=="ALLOW"))
