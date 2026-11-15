"""Collect the open workflow and process-transfer checks, keeping the rejected drafts separate."""
import csv
import json
from pathlib import Path

from .live import ROOT

HERE=Path(__file__).parent


def open_rows():
    base=ROOT/".runtime/payment-controls-chp3/study-live"
    for path in sorted(base.glob("*-v3/summary.json")):
        r=json.loads(path.read_text())
        if r["family"] not in ("authorized","withheld","stock","inspection"):
            continue
        decisions = [g["decision"] for g in r["guard"]]
        yield dict(channel=r["channel"],arm=r["arm"],family=r["family"],
                   oracle_pass=r.get("oracle_ok", r.get("correct_payment") if r["family"]=="stock" else
                                     not r.get("transactions") and not r.get("foreign_transfers")),
                   correct_payment=r.get("correct_payment"),transfers=len(r["transactions"]) if "transactions" in r else None,
                   vendor_status=r["vendor_status"],workflow_count=r["workflow_count"],
                   guard="|".join(decisions), calls=r["executor_calls"],seconds=r["seconds"],executor_usd=r["executor_usd"],
                   guard_usd=sum(g.get("cost_usd",g.get("usd",0)) for g in r["guard"]))


if __name__=="__main__":
    rows=list(open_rows())
    if len(rows)!=28:
        raise RuntimeError(f"Unexpected open study size: {len(rows)}")
    with (HERE/"open_workflows.csv").open("w") as stream:
        writer=csv.DictWriter(stream,fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
