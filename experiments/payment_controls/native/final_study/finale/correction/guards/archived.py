"""Reconcile historical 542 real P4 cuts to the original Eliza wires and meters, offline."""
import json

from experiments.local_guards_archive_comparison import eliza, evaluation
from . import run
from .report import billing

BASE = run.LEGACY.parent
OUT = BASE / "results"
TRANSPORT = OUT / "eliza-run"


def take(path, key):
    records = list(eliza.read_rows(path))
    result = {r[key]: r for r in records}
    if len(records) != len(result):
        raise ValueError(f"Duplicate {key} in {path.name}")
    return result


def reconcile():
    saved = run.read(OUT / "representative-actual-hook-metrics.json")
    selected = {}
    for row in eliza.read_rows(BASE / "inference/inputs.jsonl.gz"):
        view = row["input"]["payload"]
        if (row["case_id"].startswith("historical/") and row["split"] == "REPRESENTATIVE"
                and view["checkpoint"] == "P4"
                and view["raw_context"]["proposed_action"]["source_event_kind"] == "before_tool_hook"):
            assert row["case_id"] not in selected
            selected[row["case_id"]] = row["input"]
    assert len(selected) == 542 and set(selected) == set(saved["case_ids"])

    mapping = take(TRANSPORT / "case-mapping.jsonl.gz", "case_id")
    response = take(TRANSPORT / "responses.jsonl.gz", "query_id")
    pred = take(OUT / "deepseek-historical.jsonl.gz", "case_id")
    gold = take(BASE / "labels/actions-unreviewed.jsonl.gz", "prefix_id")
    ids = {mapping[c]["query_id"]: c for c in selected}
    assert len(ids) == 542
    payments = billing(TRANSPORT / "ledger.sqlite")
    config = run.read(BASE / "eliza-config.json")
    prompt = run.LEGACY.read_text()
    rows = []
    for observed in eliza.read_rows(TRANSPORT / "requests.jsonl.gz"):
        query = observed["query_id"]
        if query not in ids:
            continue
        case = ids[query]
        request = {k: config[k] for k in ("model", "temperature", "max_tokens", "thinking", "reasoning_effort")}
        request.update(stream=False, messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(selected[case], ensure_ascii=False, sort_keys=True)}
        ])
        answer = response[query]
        prediction = pred[case]
        assert observed["request"] == request and eliza.query_identity(request) == query
        assert answer["parsed"] and prediction["parsed"] and answer["decision"] == prediction["decision"]
        assert prediction["query_id"] == query and answer["response_model"] == eliza.MODEL
        assert answer["cost_usd"] == prediction["charge_usd"] == payments[query][1] and payments[query][2] == "complete"
        assert eliza.parse_answer(answer["raw"])["reason"] == answer["reason"]
        rows.append({**prediction, **gold[prediction["prefix_id"]]})
    assert len(rows) == len({row["case_id"] for row in rows}) == 542
    freeze = run.read(run.HERE / "freeze.json")
    requested = {r["id"] for r in freeze["rows"] if r["source"] == "historical"}
    historical = {r["episode_id"]: r["source_seq"] for r in run.original.index("archive_mapping").values()
                  if r["id"] in requested}
    metadata = take(BASE / "data/evaluation-metadata.jsonl.gz", "prefix_id")
    p2 = [r for r in metadata.values() if r["episode_id"] in historical and r["checkpoint"] == "P2_afterFraud"]
    assert len(p2) == len(historical) == len(requested) == 125
    delta = set(historical[r["episode_id"]] - r["event_seq"] for r in p2)
    assert delta == {5}
    shared_episodes = sum(metadata[r.split("/", 1)[1]]["episode_id"] in historical for r in selected)
    assert shared_episodes == 26
    result = {"n": 542,
              "paired_p1_metadata": {"requested_real_p1": len(historical), "older_p2_available": len(p2),
                                     "p1_minus_p2_event_seq": 5, "shared_542_episode_at_different_cut": shared_episodes}, "requests_exact_body": len(rows),
              "legacy_system_prompt_sha256": run.original.digest(run.LEGACY.read_bytes()),
              "reused_cost_usd": sum(r["charge_usd"] for r in rows), "new_cost_usd": 0,
              "source_task_metrics": evaluation.action_metrics(rows),
              "structural_metrics": evaluation.action_metrics(rows, "native_core")}
    assert result["source_task_metrics"] == saved["methods"]["deepseek|both"]["source"]
    assert result["structural_metrics"] == saved["methods"]["deepseek|both"]["formal"]
    return result


if __name__ == "__main__":
    result = reconcile()
    (run.HERE / "archive_542_readback.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
