from collections import Counter
from decimal import Decimal
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

root = Path(".runtime/payment-controls-chp3/final-study-payment-finale")
release = root / "continuation-release.json"
project = Path("experiments/payment_controls/native/final_study/finale/examples")
preflight = project / "continuation_preflight.json"

def read(path):
    return json.loads(path.read_bytes())
def digest(path):
    return sha256(path.read_bytes()).hexdigest()

usage = read(root/"continuation/usage.json")
approval = read(release)
assert approval["code_sha256"] == digest(project/"continuation.py")
assert approval["preflight_sha256"] == digest(preflight)
assert approval["freeze_sha256"] == digest(root/"freeze.json")
summary = []
all_cost = Decimal(0)
for source in read(preflight):
    name = source["assignment"]
    directory = root/"continuation"/name
    historical = root/"test"/name
    closed = read(directory/"continuation.json")
    capture = read(historical/"P1-001.json")
    expected = source["first_native_request_assembled_offline"]["request_sha256_excluding_wall_clock"]
    assert closed["first_request_sha256_excluding_wall_clock"] == expected
    before = read(historical/"episode.json")
    steps = before["traces"][capture["workflow_id"]]["steps"]
    stop, = (s for s in steps if s["kind"]=="finale_payment_stop" and s["point"]=="P1")
    opened, = (s for s in steps if s["kind"]=="finale_jev" and s["point"]=="P1")
    assert opened["decision"]=="BLOCK" and opened["seq"] < stop["seq"]
    assert not any(s["kind"]=="llm" and s.get("agent")=="payments_agent" for s in steps)
    assert not before["after"]["transactions"]
    after = closed["steps"]
    evidence, = (s for s in after if s["kind"]=="tool" and s.get("name")=="get_invoice_for_payment")
    condition = evidence["output"]
    assert capture["snapshot"]["invoice"]["agent_notes"]==condition["agent_notes"]
    read_by = []
    for s in after:
        if s["kind"]!="llm" or s["seq"] <= evidence["seq"]:
            continue
        for message in s["messages"]:
            obj=message.get("output")
            if isinstance(obj,str):
                obj=json.loads(obj)
            if obj==condition:
                read_by.append(s["seq"])
                break
    decision, = (s for s in after if s["kind"]=="tool" and s.get("name")=="complete_task")
    assert decision["output"]["task_status"]=="failed" and read_by
    assert not closed["completed_receipts"]
    assert not any(call["name"]=="finstripe__create_transfer" for s in after if s["kind"]=="llm"
                   for call in s["output"]["tool_calls"])
    with sqlite3.connect((directory/"finbot.db").resolve().as_uri()+"?mode=ro",uri=True) as db:
        status, = db.execute("select status from invoices where id=? and namespace=?",
                             (capture["invoice_id"],capture["namespace"])).fetchone()
        rows = db.execute("select count(*) from payment_transactions where namespace=? and invoice_id=?",
                          (capture["namespace"],capture["invoice_id"])).fetchone()[0]
        notices = db.execute("select count(*) from emails where namespace=? and direction='outbound'",
                             (capture["namespace"],)).fetchone()[0]
        assert (status,rows,notices)==("approved",0,0)
    calls = directory/"calls.jsonl.gz"
    with gzip.open(calls, "rt") as stream:
        receipts = [r for r in map(json.loads,stream)]
    counts = Counter(r["event"] for r in receipts)
    assert counts["request"]==counts["accounting"]==3 and not counts["error"]
    cost = sum((Decimal(str(r["eliza_cost_usd"])) for r in receipts if r["event"]=="accounting"),Decimal(0))
    all_cost += cost
    summary.append({
        "historical_B_assignment":name, "historical_B_episode_sha256": source["episode_sha256"],
        "historical_B_offer_cutoff": capture["trace_cutoff_seq"], "historical_B_verdict_seq": opened["seq"],
        "historical_B_stop_seq":stop["seq"],"historical_B_payments_actor_called":False,
        "historical_B_completed_receipts":0,"selected_WAL_commit_frame":source["selected_commit_frame"],
        "stock_continuation_sha256": digest(directory/"continuation.json"),"stock_transport_sha256":digest(calls),
        "stock_first_request_sha256_excluding_wall_clock":expected,"stock_hold_tool_read_seq":evidence["seq"],
        "stock_llm_request_seqs_with_exact_hold_read":read_by,
        "stock_completion_seq":decision["seq"],"stock_completion_status":"failed","stock_final_invoice_status":status,
        "stock_transfer_proposals":0,"stock_completed_receipts":rows,"notice_evaluated":False,
        "stock_paid_model_requests":counts["accounting"],"stock_eliza_cost_usd":format(cost,".9f"),
    })
assert abs(Decimal(str(usage["continuations_delta"]["settled_usd"]))-all_cost)<Decimal("0.000000000001")
assert usage["continuations_delta"]["unresolved_usd"]==0
print(json.dumps({
    "scope":"two post-hoc isolated stock Payments child continuations after observed B stops",
    "freeze_sha256":approval["freeze_sha256"],"release_sha256":digest(release),"preflight_sha256":digest(preflight),
    "continuation_code_sha256":approval["code_sha256"],"eliza_continuation_request_count":6,
    "continuation_eliza_settled_usd":format(all_cost,".9f"),"continuation_eliza_unresolved_usd":0,
    "shared_ledger_snapshot":usage,"results":summary,
},indent=2,sort_keys=True))
