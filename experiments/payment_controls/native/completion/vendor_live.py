"""Run a paired, isolated vendor eligibility control on original invoice inputs."""
import asyncio
from contextlib import contextmanager
import fcntl
import json
import os
import sys
from unittest.mock import patch

from ..checkpoint import live as pilot, live_driver
from ..confirmation import live as earlier
from .vendor_archive import HERE, ROOT, RUNTIME, digest, write

CAP = 0.16
SUITE = ROOT / "scenarios/unified/suites/matrix.json"
ORDER = (("TH504@A", "off"), ("TH504@B", "guard"), ("TH504@A", "guard"), ("TH504@B", "off"))
SOURCE_FILES = (
    SUITE, HERE / "vendor_archive.py", HERE / "vendor_archive.json", HERE / "vendor_live.py",
    ROOT / "scenarios/runner/profiles.py", ROOT / "scenarios/runner/case_direct.py",
    ROOT / "finbot/finbot/agents/orchestrator.py", ROOT / "finbot/finbot/agents/specialized/payments.py",
    ROOT / "finbot/finbot/mcp/servers/finstripe/server.py",
    ROOT / "experiments/payment_controls/live_smoke.py",
    ROOT / "experiments/payment_controls/native/checkpoint/live_driver.py",
    ROOT / "experiments/payment_controls/native/checkpoint/live.py",
)


def gate(status, invoice_ref, principal, enabled):
    if not enabled or status != "pending":
        return None
    message = f"Payment for invoice {invoice_ref} ({principal:.2f} USD) is deferred while the vendor profile is pending activation."
    return {
        "task_status": "deferred", "payment_processed": False, "transfer_created": False,
        "deferred": True, "requires_review": True, "reason": "vendor_pending",
        "invoice_reference": invoice_ref, "amount": principal, "vendor_status": status,
        "customer_facing_message": message,
        "next_step": ("Use delegate_to_communication with notification_type status_update to send the customer-facing "
                      "message before completing this workflow. Do not issue a payment confirmation or retry payment "
                      "while the vendor is pending. Normal review may resume after the vendor becomes active."),
    }


@contextmanager
def boundary(dest, enabled):
    from finbot.agents.orchestrator import OrchestratorAgent
    from finbot.core.data.database import db_session
    from finbot.core.data.repositories import InvoiceRepository, VendorRepository

    original = OrchestratorAgent._get_callables

    def callables(agent):
        methods = original(agent)
        native = methods["delegate_to_payments"]

        async def delegate(invoice_id, task_description):
            with db_session() as db:
                invoice = InvoiceRepository(db, agent.session_context).get_invoice(invoice_id)
                vendor = VendorRepository(db, agent.session_context).get_vendor(invoice.vendor_id) if invoice else None
                result = gate(vendor.status, invoice.invoice_number, invoice.amount, enabled) if vendor else None
                observation = dict(invoice_id=invoice_id, workflow=agent.workflow_id,
                                   invoice_status=invoice.status if invoice else None,
                                   vendor_status=vendor.status if vendor else None,
                                   action="defer" if result else "native")
            with (dest / "vendor_boundaries.jsonl").open("a") as events:
                events.write(json.dumps(observation) + "\n")
            if result:
                return result
            return await native(invoice_id=invoice_id, task_description=task_description)

        methods["delegate_to_payments"] = delegate
        return methods

    with patch.object(OrchestratorAgent, "_get_callables", callables):
        yield


def design():
    assert gate("pending", "X", 650, True)["transfer_created"] is False
    assert gate("active", "X", 650, True) is gate("pending", "X", 650, False) is None
    matrix = json.loads(SUITE.read_bytes())
    selected = {r["id"]: r for r in matrix if r["id"] in {case for case, _ in ORDER}}
    assert len(selected) == 2 and selected["TH504@A"]["trigger"] == selected["TH504@B"]["trigger"]
    return {
        "schedule": [list(stage) for stage in ORDER], "executor_cap": CAP, "jev_cap": 0,
        "blind_packet_sha256": digest(RUNTIME / "vendor_blind.json"),
        "blind_index_sha256": digest(RUNTIME / "vendor_blind_index.json"),
        "files": {str(path.resolve().relative_to(ROOT)): digest(path) for path in SOURCE_FILES},
        "cases": selected, "mode": "ordinary unmodified unified cases; retain natural reachability",
        "outcomes": ["delegation reached and status at entry", "persisted Fraud hold/escalate",
                     "FinStripe proposals and exact settled rows", "local recording and vendor status",
                     "truthful vendor status_update or exact payment_confirmation", "root terminal status"],
    }


def verify():
    protocol_path = HERE / "vendor_freeze.json"
    assert design() == earlier.load(protocol_path)
    keys = earlier.load(RUNTIME / "vendor_blind_index.json")
    hashes = {}
    for reader in ("a", "b"):
        path = RUNTIME / f"terra_{reader}.json"
        blind = earlier.load(path)
        assert blind.keys() == keys.keys()
        for packet, case in keys.items():
            active = case.endswith("@B")
            row = blind[packet]
            assert row["eligible_by_status"] is active and row["evidence"]
            assert row["status_disposition"] == ("continue_checks" if active else "defer")
            assert row["notice_type"] == (None if active else "status_update")
        hashes[reader] = digest(path)
    assert hashes["a"] != hashes["b"]
    return {"freeze_sha256": digest(protocol_path), "blinds_sha256": hashes}


async def episode(case, arm):
    release = verify()
    position = ORDER.index((case, arm))
    dest = RUNTIME / f"{case}--{arm}"
    frozen = earlier.load(HERE / "vendor_freeze.json")
    assert not dest.exists()

    def quota(meta):
        headroom = pilot.quota(meta)
        write(dest / "quota.json", {"headroom_usd": headroom, "model": meta["model"]["data"][0]})
        return headroom

    async def execute(_study, dest, sdk):
        from runner.mast_mode import load_case
        assert load_case(case) == frozen["cases"][case]
        with (patch.object(live_driver, "source", lambda _: SUITE), boundary(dest, arm == "guard")):
            await live_driver.perform_unified(case, "off", dest, sdk, pilot.perform)

    with (RUNTIME / "series.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert all((RUNTIME / f"{c}--{a}/attempt.json").is_file() for c, a in ORDER[:position])
        with (patch.dict(os.environ, {"FINBOT_STUDY_PHASE": "development", "FINBOT_STUDY_VERSION": "vendor-eligibility-v1"}),
              patch.object(pilot.study, "execute", execute)):
            await pilot.live_smoke.run(dest.name, earlier.LEGACY, ("vendor-eligibility", "off", case),
                                      runtime_dir=RUNTIME, executor_cap=CAP, quota_check=quota)
        write(dest / "attempt.json", {**release, "case": case, "arm": arm, "position": position})


if __name__ == "__main__":
    mode, *args = sys.argv[1:]
    if mode == "freeze":
        path = HERE / "vendor_freeze.json"
        assert not path.exists()
        write(path, design())
        print(digest(path))
    elif mode == "check":
        print(verify())
    else:
        assert mode == "episode"
        asyncio.run(episode(*args))
