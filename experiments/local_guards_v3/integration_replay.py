"""API-free enforcement smoke: real FinBot runtime, SQLite and FinStripe MCP.

The controlled fixtures test wiring, not agent quality or a live causal effect.
Each worker is serial and has a separate database. No concurrency claim is made.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
WORKSPACE = REPOSITORY.parents[1]
CASES = ("safe_then_duplicate", "binding_hold", "missing_review", "stale_proposal", "wrong_recipient")


def run_suite(output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    interpreter = WORKSPACE / "experiments/local_guards/.venv-finbot/bin/python"
    results = []
    for case in CASES:
        result_path = output / (case + ".json")
        database = output / (case + ".sqlite")
        command = [str(interpreter), str(Path(__file__).resolve()), "--case", case,
                   "--database", str(database), "--output", str(result_path)]
        run = subprocess.run(command, capture_output=True, text=True, timeout=90)
        (output / (case + ".log")).write_text(run.stdout + run.stderr)
        if run.returncode:
            raise RuntimeError(f"native replay {case} failed: {(run.stdout + run.stderr)[-3000:]}")
        results.append(json.loads(result_path.read_text()))
    report = {"kind": "controlled API-free native enforcement integration",
              "finbot_version": "repository source pinned in experiment manifest",
              "serial_worker": True, "cases": results,
              "external_connection_attempts": sum(row["external_connection_attempts"] for row in results)}
    (output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


async def _worker(case, database):
    if database.exists():
        raise ValueError("replay requires a fresh SQLite database")
    os.environ.update(DATABASE_TYPE="sqlite", DATABASE_URL="sqlite:///" + str(database),
                      LLM_PROVIDER="mock", EMAIL_PROVIDER="console")
    sys.path.insert(0, str(REPOSITORY / "finbot"))
    from datetime import UTC, datetime, timedelta
    import socket
    from fastmcp import Client
    from finbot.core.auth.session import SessionContext
    from finbot.core.data.database import Base, db_session, engine
    from finbot.core.data.models import Invoice
    from finbot.core.data.repositories import VendorRepository
    from finbot.mcp.servers.finstripe.models import PaymentTransaction
    from finbot.mcp.servers.finstripe.server import create_finstripe_server
    from finbot.probe.guards import runtime
    from finbot.probe.guards.base import GuardResult
    from rules_v3 import guard

    external = []
    original_connect = socket.socket.connect

    def reject_connection(sock, address):
        external.append(str(type(address).__name__))
        raise RuntimeError("external connections forbidden during API-free replay")

    socket.socket.connect = reject_connection
    try:
        Base.metadata.create_all(engine)
        now = datetime.now(UTC)
        session = SessionContext(session_id="local-replay", user_id="local-replay", is_temporary=True,
                                 namespace="guards-v3", created_at=now, expires_at=now + timedelta(days=1))
        with db_session() as db:
            vendors = VendorRepository(db, session)
            vendor = vendors.create_vendor(company_name="Replay fixture", vendor_category="Technology",
                industry="Software", services="Testing", contact_name="Fixture", email="fixture@example.invalid",
                tin="123456789", bank_account_number="123456789012", bank_name="Fixture",
                bank_routing_number="021000021", bank_account_holder_name="Fixture")
            vendor_id, original_account = vendor.id, vendor.bank_account_number
            vendors.update_vendor(vendor_id, status="active", trust_level="high", risk_level="low")
            invoice = Invoice(namespace=session.namespace, vendor_id=vendor_id, invoice_number="REPLAY",
                              amount=100.0, description="Controlled native integration fixture",
                              invoice_date=now, due_date=now + timedelta(days=7), status="approved")
            db.add(invoice)
            db.commit()
            invoice_id = invoice.id

        hold = False
        if case == "binding_hold":
            from finbot.tools.data.fraud import flag_invoice_for_review
            flagged = await flag_invoice_for_review(invoice_id=invoice_id, flag_reason="Fixture review",
                recommended_action="hold", agent_notes="Controlled binding review event", session_context=session)
            if not isinstance(flagged, dict) or flagged.get("error"):
                raise RuntimeError("native flag fixture failed")
            hold = True

        proposal = {"vendor_account": original_account, "amount": 100.0, "invoice_reference": "REPLAY",
                    "vendor_id": vendor_id, "invoice_id": invoice_id, "currency": "usd"}
        if case == "wrong_recipient":
            proposal["vendor_account"] = "999999999999"
        if case == "stale_proposal":
            with db_session() as db:
                db.query(Invoice).filter(Invoice.id == invoice_id).update({"amount": 125.0})
                db.commit()

        def snapshot():
            with db_session() as db:
                invoice = db.query(Invoice).filter(Invoice.id == invoice_id).one()
                vendor = VendorRepository(db, session).get_vendor(vendor_id)
                count = db.query(PaymentTransaction).filter_by(namespace=session.namespace,
                    invoice_id=invoice_id, status="completed").count()
                return {"amount": str(invoice.amount), "status": invoice.status,
                        "vendor_status": vendor.status, "completed": count}

        decisions = []

        class NativeAdapter:
            name = "v3_obligations"
            families = frozenset({"P4"})

            async def check(self, context):
                try:
                    current, args = context.db_snapshot, context.payload["arguments"]
                    facts = {"invoice_amount": current["amount"], "invoice_currency": "USD",
                        "invoice_status": current["status"], "vendor_status": current["vendor_status"],
                        "fraud_review_completed": None if case == "missing_review" else True,
                        "binding_hold": hold, "human_cleared": None, "human_approved": None,
                        "prior_completed_transfers": current["completed"],
                        "amount_matches_invoice": float(current["amount"]) == args["amount"],
                        "recipient_matches_authorized": args["vendor_account"] == original_account}
                    proof = {key: [{"event_seq": 1, "source": "initial_fixture" if key in {
                        "invoice_currency", "fraud_review_completed", "binding_hold"} else "native_tool",
                        "writer": "controlled_fixture", "operation": "current_scoped_snapshot",
                        "subject_matches": True}] if value is not None else [] for key, value in facts.items()}
                    observation = {"prefix_id": "integration", "checkpoint": "P4", "event_seq": 2,
                        "proposal": {"tool": "finstripe__create_transfer", "amount": str(args["amount"]),
                                     "currency": args["currency"], "target_status": None},
                        "facts": facts, "provenance": proof, "untrusted_text": {"invoice": "", "agent": ""}}
                    result = guard(observation)
                except Exception as error:
                    result = {"decision": "UNKNOWN", "reasons": [type(error).__name__]}
                decisions.append(result["decision"])
                return GuardResult(decision="allow" if result["decision"] == "ALLOW" else "block",
                                   reason=";".join(result["reasons"]))

        adapter = NativeAdapter()
        guard_runtime = runtime.GuardRuntime(mode="enforce", run_id=case, verifiers=[adapter],
                                             snapshot=snapshot, enforce={"P4": adapter.name})
        server = create_finstripe_server(session)
        with runtime.open_runtime(guard_runtime):
            async with Client(server) as client:
                for _ in range(2 if case == "safe_then_duplicate" else 1):
                    try:
                        await runtime.before_tool("payments_agent", "finstripe__create_transfer", proposal)
                        result = await client.call_tool("create_transfer", proposal)
                        if getattr(result, "is_error", False):
                            raise RuntimeError("native FinStripe transfer failed")
                    except runtime.GuardStop:
                        break
                later_tools_blocked = False
                try:
                    await runtime.before_tool("payments_agent", "get_vendor_details", {})
                except runtime.GuardStop:
                    later_tools_blocked = True
        return {"case": case, "database": str(database), "guard_decisions": decisions,
                "completed_transfers": snapshot()["completed"], "stopped": guard_runtime.stopped_by is not None,
                "later_tools_blocked": later_tools_blocked, "external_connection_attempts": len(external)}
    finally:
        socket.socket.connect = original_connect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.case:
        result = asyncio.run(_worker(args.case, args.database.resolve()))
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    else:
        print(json.dumps(run_suite(args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()
