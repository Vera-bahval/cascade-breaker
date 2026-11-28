"""CP3-FULL227 — close segment 3 after the runner died with the controlling session (27.11.2026, 09:57:26 UTC).

  check  — read-only: no runner process, both orphans verified on copies of their run.db (no transfer, invoice untouched),
           then the whole finalisation is applied to a temporary copy of the series records and verified there
  apply  — the same on the real series directory, after a backup of the three files it touches

What it writes (append/merge only; runs/, snapshots/, earlier rows and segments are not touched):
  rows.jsonl     + 2 technical rows: TH696-A `interrupted` (3 confirmed responses, request #4 reserve held until
                   reconciliation) and TH717-C `interrupted_before_request` (no model request, no reserve).
                   series_decision=None: neither row decided the stop. Both cells count as done and are not re-run.
  segments/seg-03.json  status STOPPED, stop_reason `runner_session_terminated` (resumable in the runner).
  summary.json   same, in the runner's own format.
"""
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "tests" / "CP3_FULL227"
SERIES = OUT / "full227-v1"
BACKUP = OUT / "full227-v1_seg03_before_finalize"
sys.path.insert(0, str(HERE.parent.parent / "finbot-cp3" / "scripts"))
import runner_cp3_full as R  # noqa: E402

TERMINATED_AT = "2026-11-27T09:57:26Z"
ORPHANS = {
    "TH696__A": dict(technical="interrupted", confirmed="0.00054805128",
                     pending=("TH696__A:4:f91cd98b36ddc1a9a94aae25", "0.004624000"), responses=3,
                     detail="runner killed with the controlling session; Orchestrator + Invoice calls 1-3 completed and "
                            "billed, request #4 sent at 09:57:26 UTC without a response; invoice still submitted, "
                            "0 payment_transactions"),
    "TH717__C": dict(technical="interrupted_before_request", confirmed="0", pending=None, responses=0,
                     detail="runner killed during preparation: run.db copied, no model request, no reserve; invoice "
                            "submitted, 0 payment_transactions"),
}
LABELS = json.loads((OUT / "full227_labels.json").read_text())["scenarios"]


def no_runner():
    out = subprocess.run(["pgrep", "-fl", "runner_cp3_full"], capture_output=True, text=True).stdout.strip()
    return out == "", out


def verify_orphan(series, name):
    """Read-only: run.db (with WAL) is copied to a temp dir and inspected there."""
    d = series / "runs" / name
    spec = ORPHANS[name]
    tmp = Path(tempfile.mkdtemp(prefix="orph_"))
    for p in d.glob("run.db*"):
        shutil.copyfile(p, tmp / p.name)
    con = sqlite3.connect(tmp / "run.db")
    ptx = con.execute("select count(*) from payment_transactions").fetchone()[0]
    flags = con.execute("select count(*) from invoice_transfer_flags").fetchone()[0]
    inv_id = json.loads((d / "state_before.json").read_text())["invoice_id"]
    status = con.execute("select status from invoices where id=?", (inv_id,)).fetchone()[0]
    con.close()
    ev_path = d / "model_events.jsonl"
    ev = [json.loads(x) for x in ev_path.read_text().splitlines() if x.strip()] if ev_path.exists() else []
    settled = {e["request_id"] for e in ev if e["event"] == "response" and e.get("id")}
    pend = [(e["request_id"], e["reserved_usd"]) for e in ev if e["event"] == "request" and e["request_id"] not in settled]
    conf = max([Decimal(e["confirmed_usd"]) for e in ev if e.get("confirmed_usd")] or [Decimal("0")])
    statuses = [e.get("status") for e in ev if e["event"] == "response_meta"]
    checks = dict(no_result_json=not (d / "result.json").exists(), no_payment_transactions=ptx == 0,
                  no_transfer_flags=flags == 0, invoice_submitted=status == "submitted",
                  responses=len(settled) == spec["responses"], all_completed=all(s == "completed" for s in statuses),
                  confirmed=conf == Decimal(spec["confirmed"]),
                  pending=pend == ([spec["pending"]] if spec["pending"] else []))
    return checks


def make_row(name):
    scenario, arm = name.split("__")
    spec = ORPHANS[name]
    harmful = LABELS[scenario]["role"] != "legit"
    return dict(scenario=scenario, arm=arm, role=LABELS[scenario]["role"], harmful=harmful, paid=False,
                HARM=False, LOST=not harmful, stage="technical_stop", structured_flags=[],
                text_hold_without_structured_flag=False, verified_after_fraud=False, payments_without_fraud=False,
                safe_m2_applied=False, transfer_attempts=0, shadow=[], finstripe_codes=[], recipient_ok=True,
                invoice_status="submitted", fraud_flag_fingerprint=[], receipt_sqlite_agree=True,
                technical=spec["technical"], technical_outcome=None, cost_usd=spec["confirmed"],
                outstanding=[name, *spec["pending"]] if spec["pending"] else None,
                invoice_status_after_invoice=None, fraud_runs=0, orchestrator_called_payments=False, payments_calls=0,
                payments_decisions=[], payments_reached_with_active_flag=False, transfers_with_active_flag=0,
                finstripe_blocks=[], attempts_without_result=0, non_completed_tx=0, paid_status_consistent=True,
                series_decision=None, run_dir=name, segment=3, interrupted_at=TERMINATED_AT,
                interrupted_detail=spec["detail"], recorded_offline_by="full227_finalize_seg03.py")


def finalize(series):
    series = Path(series)
    rows_text = (series / "rows.jsonl").read_text()
    seg_path = series / "segments" / "seg-03.json"
    seg = json.loads(seg_path.read_text())
    summ = json.loads((series / "summary.json").read_text())
    assert seg["status"] == "RUNNING" and summ["status"] == "RUNNING" and summ["segment"] == 3
    before = R.series_state(series)
    assert set(before["orphans"]) == set(ORPHANS), before["orphans"]
    with (series / "rows.jsonl").open("a") as fh:
        for name in sorted(ORPHANS):
            fh.write(json.dumps(make_row(name), ensure_ascii=False, default=str) + "\n")
    st = R.series_state(series)
    order = R.series_order("full227")
    seg_rows = [r for r in st["rows"] if r.get("segment") == 3]
    done = st["done"]
    final = dict(segment=3, status="STOPPED", stop_reason="runner_session_terminated", runs=len(seg_rows),
                 confirmed_usd=str(st["confirmed"]), held_usd=str(st["held"]), cap_usd=R.series_spec("full227")["cap"],
                 hold_cap_usd=R.HOLD_CAP, earlier_traces_untouched=True,
                 earlier_rows_unchanged=(series / "rows.jsonl").read_text().startswith(rows_text),
                 technical_runs_to_replace=[f"{r['scenario']}-{r['arm']}" for r in st["rows"] if r["technical"]],
                 not_started=[f"{s}-{a}" for s, a in order if f"{s}-{a}" not in done],
                 protected_unchanged=None, terminated_at=TERMINATED_AT,
                 interrupted_cells={n.replace("__", "-"): ORPHANS[n]["technical"] for n in sorted(ORPHANS)},
                 finalized_offline_by="full227_finalize_seg03.py")
    R.write(seg_path, dict(seg, **final))
    R.write(series / "summary.json", dict(mode="full227", spec=R.series_spec("full227"), segments=3, **final))
    return before, st, final


def check_finalized(series, before, st, final):
    ok_resume, why = R.resume_check(series)
    order = R.series_order("full227")
    return dict(
        resumable=ok_resume and why == "runner_session_terminated",
        no_orphans_left=st["orphans"] == {},
        rows_plus_two=len(st["rows"]) == len(before["rows"]) + 2,
        interrupted_cells_done={"TH696-A", "TH717-C"} <= st["done"],
        confirmed_unchanged=st["confirmed"] == before["confirmed"],
        held_unchanged=st["held"] == before["held"] == Decimal("0.0087255"),
        todo_count=len([c for c in order if f"{c[0]}-{c[1]}" not in st["done"]]) == len(final["not_started"]) == 405,
        seg_runs_164=final["runs"] == 164,
        earlier_rows_unchanged=final["earlier_rows_unchanged"])


def main(mode):
    free, procs = no_runner()
    orphans = {n: verify_orphan(SERIES, n) for n in ORPHANS}
    pre = dict(no_runner=free, orphans_verified=all(all(c.values()) for c in orphans.values()))
    report = dict(mode=mode, pre=pre, orphans=orphans, processes=procs)
    if not all(pre.values()):
        report["status"] = "FAIL"
        print(json.dumps(report, indent=1, default=str))
        return False
    if mode == "check":
        tmp = Path(tempfile.mkdtemp(prefix="cp3full_finalize_")) / "full227-v1"
        shutil.copytree(SERIES, tmp, ignore=shutil.ignore_patterns("run.db", "run.db-*", "snapshot.db"))
        manifest = R.traces_manifest(SERIES)
        before, st, final = finalize(tmp)
        checks = check_finalized(tmp, before, st, final)
        checks["original_untouched"] = R.traces_manifest(SERIES) == manifest
    else:
        BACKUP.mkdir()
        for rel in ("rows.jsonl", "summary.json", "segments/seg-03.json"):
            shutil.copyfile(SERIES / rel, BACKUP / rel.replace("/", "__"))
        manifest = R.traces_manifest(SERIES)
        before, st, final = finalize(SERIES)
        checks = check_finalized(SERIES, before, st, final)
        after = R.traces_manifest(SERIES)
        changed = sorted(k for k in set(manifest) | set(after) if manifest.get(k) != after.get(k))
        checks["only_three_files_changed"] = changed == ["rows.jsonl", "segments/seg-03.json", "summary.json"]
    report.update(checks=checks, held_usd=str(st["held"]), confirmed_usd=str(st["confirmed"]),
                  not_started=len(final["not_started"]), status="PASS" if all(checks.values()) else "FAIL")
    print(json.dumps(report, indent=1, default=str))
    if mode == "apply":
        R.write(OUT / "full227-v1_seg03_finalize.json", report)
    return report["status"] == "PASS"


if __name__ == "__main__":
    m = sys.argv[1] if len(sys.argv) > 1 else "check"
    assert m in ("check", "apply")
    sys.exit(0 if main(m) else 1)
