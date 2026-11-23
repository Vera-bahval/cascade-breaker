"""Run frozen functions on the decision-time packet. Join the gold only after prediction."""
import json
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from .archive import HERE, NATIVE, write_rows

ROOT = NATIVE.parents[2]
sys.path[:0] = [str(ROOT / "finbot"), str(ROOT / "scenarios")]
from experiments.payment_controls.native import verifier
from experiments.payment_controls.native.overnight import route
from experiments.payment_controls.native.replay import local_rule
from .placement import assess


def predict(packet):
    facts = packet["state"]
    action = packet["proposed_action"]
    point = packet["point"]
    if point.startswith("P1."):
        body = {**facts, "proposal": action}
        result, reasons, _ = route.evaluate(body)
        if result == "CLOSE_ALLOW" and route.mandatory_veto(body, reasons):
            return "DEFER", "mandatory_veto"
        # A saved packet contains no running agent/workflow; the live settlement
        # binding and subsequent notification must still be tested in a live route.
        return result, ", ".join(reasons) or "supported_rule_closure"

    from finbot.mcp.servers.taxcalc.server import DEFAULT_CONFIG
    inv, vendor = facts["inv"], facts["vendor"]
    # The isolated corpus calls create_taxcalc_server(session) with no overrides.
    # Neither live workflow outcomes nor today's environment supply this setting.
    snapshot = dict(invoice=inv, vendor=vendor, other_invoices=[r for r in facts["paid"] if r["id"] != inv["id"]],
                    transactions=[t for t in facts["transactions"] if t["invoice_id"] == inv["id"]],
                    tax_configuration={"enabled": True, "config": DEFAULT_CONFIG})
    steps = []
    for flag in facts["fraud_flags"]:
        args = {k: flag[k] for k in ("invoice_id", "flag_reason", "recommended_action")}
        steps.append(dict(kind="tool", name="flag_invoice_for_review", seq=flag["seq"], arguments=args, error=False))
    completion = facts["fraud_return"]
    assert completion["invoice_id"] == inv["id"]
    steps.append(dict(kind="summary", agent="fraud_agent", task_status=completion["task_status"],
                      task_summary=completion["summary"]))
    family = point.split(".")[0]
    payload = dict(task_status=completion["task_status"], task_summary=action["summary"]) if family == "P2" else action
    ctx = SimpleNamespace(point=point, family=family, db_snapshot=snapshot, payload=payload, trace_so_far=steps)
    try:
        body = verifier.inputs(ctx)
    except KeyError as exc:
        field = exc.args[0]
        if "vendor." + field not in facts.get("field_availability", {}):
            raise
        return "UNSUPPORTED", "verifier.inputs: missing vendor." + field
    return assess(body)


def effect(point, prediction):
    if prediction == "UNSUPPORTED":
        return "not_executed"
    if point.startswith("P1"):
        return {"DEFER":"refer_to_Fraud","CLOSE_ALLOW":"close_Fraud_allow","CLOSE_STOP":"close_Fraud_stop_candidate"}[prediction]
    return "pass_without_intervention" if prediction == "DEFER" else "terminal_stop"


def describe(point, prediction, gold):
    options = gold["admissible_actions"]
    if prediction == "UNSUPPORTED":
        return "input_unavailable"
    if point.startswith("P1"):
        if prediction not in options:
            return "outside_admissible_set"
        return "set_compatible" if len(options) > 1 else "exact"
    if prediction == "DEFER":
        return "passed_admissible_step" if "ALLOW" in options else "missed_required_intervention"
    if prediction not in options:
        return "stopped_with_different_class" if "ALLOW" not in options else "false_stop"
    return "exact"


def main():
    def read(name):
        return json.loads((HERE / name).read_text())
    packets = read("packets.json")
    # No metadata, author labels, later actions, public target names or outcomes enter either method.
    predictions = {key: predict(value) for key, value in packets.items()}
    index, gold = read("corpus_index.json"), read("gold.json")
    assert set(packets) == set(index) == set(gold) and len(packets) == 28
    rows = []
    for key, (prediction, reason) in predictions.items():
        meta, g = index[key], gold[key]
        point = packets[key]["point"]
        rows.append(dict(source="controlled_packet", id=key, point=point, mechanism=meta["mechanism"],
                         operation=meta["operation"], method="pre_fraud_rule" if point.startswith("P1") else "placement.assess",
                         prediction=prediction, workflow_effect=effect(point,prediction),
                         gold="/".join(g["admissible_actions"]), comparison=describe(point,prediction,g),
                         reason=reason, partial_rule=""))
    historical = json.loads((NATIVE / "replay_packets.json").read_text())
    for record in historical:
        body = record["packet"]
        f = body["state"]["records"]
        assert f["completed_transfers"] is None and f["tax_configuration"] is None
        evidence = local_rule(body)
        assert evidence["decision"] == record["rule"]["decision"]
        rows.append(dict(source="archived_prefix", id=record["id"], point=body["state"]["point"],
                         mechanism=record["group"], operation="propose_transfer", method="placement.assess",
                         prediction="UNSUPPORTED", workflow_effect="not_executed", gold=record["gold"],
                         comparison="incomplete_archive", reason=", ".join(evidence["missing_full_method_operands"]),
                         partial_rule=evidence["decision"] + " | " + ", ".join(evidence["reasons"])))
    rows.sort(key=lambda r: (r["source"],r["point"],r["mechanism"],r["operation"],r["id"]))
    write_rows(HERE / "coverage_predictions.csv", rows)
    for group in ("P1","P2","P4"):
        subset = [r for r in rows if r["source"]=="controlled_packet" and r["point"].startswith(group)]
        print(group, Counter(r["prediction"] for r in subset), Counter(r["comparison"] for r in subset))


if __name__ == "__main__":
    main()
