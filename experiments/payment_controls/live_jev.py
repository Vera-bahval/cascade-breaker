"""P2b verifier for the two fixed synthetic document integration cases."""
import json
import math
import os
import time

import httpx

from experiments.local_guards_archive_comparison import eliza
from experiments.payment_controls.pilot import packets
from experiments.payment_controls.probe_models import PRICE, request_body
from finbot.probe.guards.base import GuardResult
from finbot.probe.guards.runtime import GuardRuntime, open_runtime


def document_runtime(case_id, folder, invoice_ref):
    document_case = {"release-note": "S01", "active-note": "S12"}[case_id]
    row, = (r for r in packets() if r["case_id"] == document_case and r["form"] == "evidence" and not r["summary"])
    # This source is the study's frozen, authenticated fixture, linked at invoice creation.
    # The case label, expected outcome, and the fixture author's summary are never transmitted.
    class DocumentVerifier:
        name = "TypeSafe-document"
        families = {"P2"}

        async def check(self, ctx):
            if not invoice_ref.get("id") or ctx.db_snapshot != invoice_ref:
                raise RuntimeError("Missing invoice binding")
            inp = {**row["input"], "state": {**row["input"]["state"], "workflow_stage": ctx.point}}
            body = request_body("jev", inp)
            identity = eliza.query_identity({"case_id": case_id, "invoice": invoice_ref, "body": body})
            ledger = eliza.Ledger(folder.parent / "live-jev.sqlite", .01)
            key = os.environ["TYPESAFE_API_KEY"]
            async with httpx.AsyncClient(trust_env=False, timeout=60, follow_redirects=False) as client:
                ledger.reserve(identity, 65536 * PRICE)
                start = time.perf_counter()
                reply = await client.post("https://api.typesafe.ai/v1/systemone", json=body,
                                          headers={"Authorization": "Bearer " + key})
                elapsed = time.perf_counter() - start
            reply.raise_for_status()
            raw = reply.json()
            tokens = raw["usage"]["input_tokens"]
            if type(tokens) is not int or tokens < 0:
                raise ValueError("Missing Jev usage")
            ledger.complete(identity, tokens * PRICE)
            (folder / "jev_receipt.json").write_text(json.dumps({"id": identity, "case": document_case,
                "invoice": invoice_ref, "request": body, "response": {k:raw.get(k) for k in ("answers","model","usage")},
                "duration_s": elapsed, "cost_estimate_usd": tokens * PRICE}, indent=2))
            if raw["model"] != "jev-1.14.0":
                raise ValueError("Served Jev version changed")
            answer = raw["answers"]["check"]
            choices = {"active_hold": "block", "no_active_hold": "allow", "insufficient_records": "review"}
            if set(answer["probabilities"]) != set(choices) or not math.isclose(sum(answer["probabilities"].values()), 1, abs_tol=.001):
                raise ValueError("Invalid response distribution")
            return GuardResult(decision=choices[answer["choice"]], reason=answer["choice"],
                               tokens_in=tokens, tokens_out=raw["usage"]["output_tokens"], cost_usd=tokens * PRICE)

    v = DocumentVerifier()
    return open_runtime(GuardRuntime("enforce", case_id, [v], lambda: dict(invoice_ref), {"P2.fraud_agent": v.name}))
