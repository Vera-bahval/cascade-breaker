"""Read each frozen P4 proposal and its own tool result. Write only non-textual research fields."""
import csv
import gzip
import hashlib
import json
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

from experiments.local_guards_final_replay.early import ROOT, TRANSFER, parse_result, raw_episodes

OUT = Path(__file__).resolve().parent
EXP = ROOT / "experiments"
INVENTORY = EXP / "local_guards_adapter_repair/inventory.json"
RECORDS = EXP / "local_guards_completion/records.jsonl.gz"
LABELS = EXP / "payment_controls/study/archive_decisions.csv"


def read_json(path):
    return json.loads(path.read_bytes())


def money(value):
    try:
        return Decimal(str(value)) if value is not None else None
    except InvalidOperation:
        return None


def match(a, b):
    return None if a is None or b is None else str(a) == str(b)


def observation(raw, index, legacy):
    if legacy:
        pos = next(i for i, s in enumerate(raw) if s["seq"] == index)
        call = raw[pos]
        if call["kind"] == "tool" and call["name"] == TRANSFER:
            return call.get("arguments", {}), parse_result(call.get("output")), index, bool(call.get("error")), "same_tool"
        assert call.get("point") == "P4." + TRANSFER
        arguments = call["payload"]["arguments"]
        for e in raw[pos+1:]:
            if e["kind"] == "guard":
                continue
            if e["kind"] == "guard_stop" and e.get("point") == "P4." + TRANSFER:
                return arguments, {}, e["seq"], False, "explicit_guard_stop"
            if e["kind"] == "tool" and e.get("name") == TRANSFER and e.get("arguments") == arguments:
                return arguments, parse_result(e.get("output")), e["seq"], bool(e.get("error")), "same_arguments"
            break
        return arguments, {}, None, False, "unjoined"
    call = raw[index - 1]
    assert call.get("tool_name") == TRANSFER
    arguments = call.get("tool_arguments") or {}
    if call['hook_kind'] == 'after_tool':
        return arguments, parse_result(call.get('tool_result')), index, bool(call.get('error')), 'same_tool'
    assert call['hook_kind'] == 'before_tool'
    for n, e in enumerate(raw[index:], index + 1):
        if e['hook_kind'] == 'after_tool' and e.get("tool_name") == TRANSFER and e.get("tool_arguments") == arguments:
            if call.get("tool_call_id") and e.get("tool_call_id") and call["tool_call_id"] != e["tool_call_id"]:
                break
            return arguments, parse_result(e.get('tool_result')), n, bool(e.get('error')), 'same_arguments'
        if e['hook_kind'] in ('before_tool', 'before_model', 'after_model'):
            break
    return arguments, {}, None, False, 'unjoined'


def build():
    inventory = read_json(INVENTORY)
    metadata = {r["metadata"]["episode_id"]:r["metadata"] for r in inventory["p4"]}
    inputs = {r["prefix_id"]:r for r in map(json.loads, gzip.open(RECORDS))}
    with LABELS.open() as f:
        labels = {r["prefix"]:r for r in csv.DictReader(f)}
    episodes = [inventory["early_episodes"][key] for key in metadata]
    rows = []
    for ep, raw, initial, _ in raw_episodes(episodes, ROOT):
        meta = metadata[ep["episode_id"]]
        record = inputs[meta["prefix_id"]]
        label = labels[meta["prefix_id"]]
        obs = record["observation"]
        facts = obs["facts"]
        args, receipt, line, error, binding = observation(raw, meta["source_event_index"], initial is not None)
        receipt = receipt if isinstance(receipt,dict) else {}
        offered = obs["tool_arguments"]
        assert money(offered["amount"]) == money(args.get("amount"))
        mismatch = money(offered["amount"]) != money(facts["invoice_amount"])
        bank_ok = match(offered.get("vendor_account"), facts.get("account"))
        principal_ok = money(receipt.get("amount")) == money(args["amount"]) if receipt.get("amount") is not None else None
        receipt_bank = match(receipt.get("vendor_account"), args.get("vendor_account"))
        ref_ok = match(receipt.get("invoice_reference"), args.get("invoice_reference"))
        cur_ok = str(receipt.get("currency") or "").upper() == str(args.get("currency") or "USD").upper()
        if binding == "explicit_guard_stop":
            outcome = "stopped_before_tool"
        elif error or receipt.get("error"):
            outcome = "tool_error"
        elif receipt.get("status") == "completed" and receipt.get("transfer_id"):
            outcome = "confirmed" if all(x is True for x in (principal_ok,receipt_bank,ref_ok,cur_ok)) else "completed_partial_binding"
        else:
            outcome = "no_linked_completion"
        rows.append(dict(prefix=meta["prefix_id"], episode=ep["episode_id"], group=record["group_id"],
                         proposal_index=meta["source_event_index"], result_index=line, source_sha256=meta["source_sha256"],
                         member_sha256=ep["raw_hash"],result_binding=binding,outcome=outcome,substantive=label["substantive"],
                         amount_disagrees=mismatch, bank_disagrees=None if bank_ok is None else not bank_ok,
                         invoice_id_disagrees=match(offered.get("invoice_id"),obs["context"].get("invoice_id")) is False,
                         vendor_id_disagrees=match(offered.get("vendor_id"),obs["context"].get("vendor_id")) is False,
                         reference_disagrees=match(offered.get("invoice_reference"),facts.get("invoice_number")) is False,
                         status_processing=facts["invoice_status"] == "processing",vendor_pending=facts["vendor_status"]=="pending",
                         archived_binding_hold=facts["binding_hold"],visible_prior=facts["prior_completed_transfers"]>0,
                         old_tax_check_unsatisfied=not facts["tax_verification_satisfied"]))
    assert len(rows)==len({r["prefix"] for r in rows})==542
    rows.sort(key=lambda r:r["prefix"])
    with (OUT/'census.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,rows[0]);writer.writeheader();writer.writerows(rows)
    conditions=['amount_disagrees','bank_disagrees','reference_disagrees','invoice_id_disagrees','vendor_id_disagrees',
                'status_processing','vendor_pending','archived_binding_hold','visible_prior','old_tax_check_unsatisfied']
    def count(field):
        return dict(Counter(r[field] for r in rows))
    summary={"total":len(rows),"outcomes":count('outcome'),"joins":count('result_binding'),
             "by_substantive":{ref:dict(Counter(r["outcome"] for r in rows if r["substantive"]==ref)) for ref in sorted(count("substantive"))},
             "conditions":{c:{"proposed":sum(r[c] is True for r in rows),
                              "receipt_confirmed":sum(r[c] is True and r["outcome"]=="confirmed" for r in rows),
                              "distinct_confirmed_groups":len({r["group"] for r in rows if r[c] is True and r["outcome"]=="confirmed"})} for c in conditions},
             "input_sha256":{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in (INVENTORY,RECORDS,LABELS)}}
    (OUT/'census.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    print(json.dumps(summary['outcomes']))


if __name__ == '__main__':
    build()
