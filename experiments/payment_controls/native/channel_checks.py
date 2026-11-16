"""Evaluate routine-channel repetitions without adding families to the denominator."""
import json
from .batch import HERE,RUNTIME,VERSION
from experiments.payment_controls.study.score import workflow_evidence
from experiments.payment_controls.study.enforce import POINTS


def check():
    rows=[]
    for channel in ("direct","portal","chat","onboarding"):
        folder=RUNTIME/f"{channel}-off-e04b3edc417640-{VERSION}"
        r=json.loads((folder/"summary.json").read_text())
        intake=json.loads((folder/"native-intake.jsonl").read_text().splitlines()[0])
        points={x["point"] for x in r["guard"] if x["reason"]!="outside_study"}
        evidence=workflow_evidence(folder,submitted_id=r["submitted_id"],expected_amount=650,
                                   registered_account=intake["vendor"]["bank_account_number"])
        rows.append(dict(channel=channel,all_points_reached=set(POINTS.values())<=points,points=sorted(points),
                         source_amount=intake["invoice"]["amount"],status=intake["vendor"]["status"],
                         trust=intake["vendor"]["trust_level"],prior_invoices=len(intake["other_invoices"]),
                         executor_usd=r["executor_usd"],seconds=r["seconds"],**evidence))
    (HERE/"channel_readiness.json").write_text(json.dumps(rows,indent=2)+"\n")


if __name__=="__main__":check()
