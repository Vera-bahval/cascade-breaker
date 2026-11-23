"""Run the native review endpoint as a constrained follow-through after a stock chat."""
import argparse
import asyncio
import hashlib
import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from experiments.payment_controls.native.completion import process_chat, selector
from experiments.payment_controls.native.completion.jev_choice import PINNED_MODEL, validate_choice
from experiments.payment_controls import live_smoke
from experiments.payment_controls.study import transfer

HERE, ROOT = selector.HERE, selector.ROOT
LIVE = selector.LIVE.parent / "completion-selector-route-v1"
FREEZE = HERE / "selector_route_freeze.json"
CAP = .065
CASES = ("review", "definition")


def exact_receipt(message):
    body = {"model": PINNED_MODEL, "state": {"message": message}, "questions": {
        "check": {"type": "choice", "instructions": selector.QUESTION, "criteria": selector.CHOICES}}}
    digest = hashlib.sha256(json.dumps(body, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    path = selector.LIVE / "jev" / (digest + ".json")
    receipt = json.loads(path.read_bytes())
    assert receipt["request_sha256"] == digest and receipt["model"] == PINNED_MODEL and receipt["valid"]
    choice, probs = validate_choice(receipt["answer"], selector.CHOICES)
    assert receipt["choice"] == choice
    return path, receipt, choice == "review" and probs["review"] >= .80


def design():
    selector.verify_freeze()
    source = json.loads((HERE / "process_chat_inputs.json").read_text())
    inputs = dict(zip(CASES, (row["message"] for row in source["cases"]), strict=True))
    receipts = {case: exact_receipt(message)[0] for case, message in inputs.items()}
    files = list((HERE / "selector_route.py", HERE / "selector_results.json",
                              HERE / "selector_freeze.json", *receipts.values()))
    files += [ROOT / filename for filename in (
        "finbot/finbot/apps/vendor/routes/api.py", "finbot/finbot/core/data/repositories.py",
        "finbot/finbot/core/auth/middleware.py", "finbot/finbot/core/auth/session.py",
        "finbot/finbot/agents/orchestrator.py", "finbot/finbot/agents/runner.py",
    )]
    return {
        "cases": list(CASES), "eliza_cap_usd": CAP, "jev_cap_usd": .006, "new_jev_requested": False,
        "scope": "same session, selected visible vendor only, existing own-vendor request-review endpoint",
        "duplicate_controls": ["skip after any upstream start attempt", "one claim per chat turn",
                               "no automatic retry after downstream error"],
        "source_sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
    }


def verify_freeze():
    assert json.loads(FREEZE.read_text()) == design()


async def follow_once(state, client, api, message):
    if state["claimed"]:
        return {"decision": "same_turn_already_handled"}
    state["claimed"] = True
    if state["upstream_attempts"]:
        return {"decision": "stock_already_attempted"}
    _, receipt, review = exact_receipt(message)
    if not review:
        return {"decision": "retain_stock", "jev": receipt}
    status = await client.get(api + "/vendors/me")
    status.raise_for_status()
    session = status.json()
    vid = session.get("current_vendor_id")
    if type(vid) is not int or vid <= 0 or vid not in {v["id"] for v in session.get("vendors", [])}:
        return {"decision": "no_bound_vendor", "jev": receipt}
    result = await client.post(f"{api}/vendors/{vid}/request-review")
    detached = {"decision": "native_review_endpoint", "http_status": result.status_code, "authorized_vendor_id": vid,
                "jev": receipt}
    if result.is_success:
        payload = result.json()
        assert payload["success"] is True and payload["vendor_id"] == vid
        detached["workflow_id"] = payload["workflow_id"]
    return detached


async def one(case):
    from experiments.payment_controls.native.checkpoint.live import quota

    verify_freeze()
    if case not in CASES:
        raise ValueError("Unknown router case")
    legacy = ROOT.parents[1] / "deepseek-flash-control-placement/experiments/control-placement/deepseek_flash"

    async def execute(study, dest, sdk):
        from finbot.agents import chat
        from runner.client import API

        state = {"upstream_attempts": 0, "claimed": False}
        original = chat.ChatAssistantBase._call_start_workflow

        async def observe(agent, description, vendor_id, invoice_id=None, attachment_file_ids=None):
            state["upstream_attempts"] += 1
            if (state["upstream_attempts"] != 1 or vendor_id != agent.session_context.current_vendor_id
                    or not vendor_id or invoice_id is not None or attachment_file_ids):
                raise ValueError("Workflow outside one session-bound profile review")
            return await original(agent, description, vendor_id, invoice_id, attachment_file_ids)

        class FollowThroughClient(httpx.AsyncClient):
            async def post(self, url, *args, **kwargs):
                response = await super().post(url, *args, **kwargs)
                if url == API + "/chat" and response.is_success:
                    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
                    if events and events[-1]["type"] == "done" and not any(e["type"] == "error" for e in events):
                        message = kwargs["json"]["message"]
                        decision = await follow_once(state, self, API, message)
                        replay = await follow_once(state, self, API, message)
                        process_chat.dump(dest / "router.json", {
                            **decision, "same_turn_repeat": replay, "upstream_attempts": state["upstream_attempts"],
                        })
                return response

        with (patch.object(process_chat, "httpx", SimpleNamespace(
                    AsyncClient=FollowThroughClient, ASGITransport=httpx.ASGITransport)),
              patch.object(chat.ChatAssistantBase, "_call_start_workflow", observe)):
            await process_chat.perform(case, "off", dest, sdk)

    with patch.object(transfer, "transport_check", execute):
        await live_smoke.run(case, legacy, ("chat-transfer", "off", case),
                             runtime_dir=LIVE, executor_cap=CAP, quota_check=quota)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "one"))
    parser.add_argument("case", nargs="?")
    args = parser.parse_args()
    if args.action == "freeze":
        if FREEZE.exists():
            verify_freeze()
        else:
            process_chat.dump(FREEZE, design())
    else:
        asyncio.run(one(args.case))


if __name__ == "__main__":
    main()
