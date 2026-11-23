import json

import pytest

from experiments.payment_controls.native.completion.jev_choice import PINNED_MODEL, receipt_probabilities, receipt_v2, validate_choice


def answer(probabilities, choice="B"):
    return {"type": "choice", "choice": choice, "confidence": .25, "probabilities": probabilities}


def test_keyed_response_out_of_order_and_tie():
    tied = answer({"C": .1, "A": .45, "B": .45})
    assert validate_choice(tied, ["B", "A", "C"]) == ("B", tied["probabilities"])
    assert validate_choice(answer({"C": .1, "B": .45, "A": .45}, "A"), "ABC")[0] == "A"


@pytest.mark.parametrize("probabilities", [
    {"A": .1, "B": .9}, {"A": .1, "B": .2, "C": .69},
    {"A": -.1, "B": .9, "C": .2}, {"A": True, "B": .0, "C": .0},
    {"A": float("nan"), "B": .9, "C": .1}, {"A": .50, "B": .49, "C": .01},
])
def test_rejects_invalid_vectors_and_winner(probabilities):
    with pytest.raises(ValueError):
        validate_choice(answer(probabilities), "ABC")


def test_preserves_near_rounding_and_backward_compatibility():
    rounded = {"C": .1001, "B": .5995, "A": .3001}
    typed = answer(rounded)
    payload = {"model": PINNED_MODEL, "answers": {"check": typed},
               "usage": {"input_tokens": 40, "output_tokens": 15}}
    receipt = receipt_v2({"questions": {"check": {"criteria": dict.fromkeys("ABC")}}},
                         json.dumps(payload).encode())
    assert receipt["answer"] == typed
    assert receipt_probabilities(receipt) == rounded
    assert receipt_probabilities({"choice": "B", "probabilities": rounded}) == rounded
    assert receipt_probabilities({"choice": "B"}) is None


def test_research_client_stores_paid_response_and_reuses_only_valid_receipt(tmp_path):
    import httpx

    from experiments.local_guards_archive_comparison.eliza import Ledger
    from experiments.payment_controls.native.completion.jev_choice import call_v2

    calls = []

    def transport(request):
        calls.append(request)
        assert (request.method, str(request.url)) == ("POST", "https://api.typesafe.ai/v1/systemone")
        bad = json.loads(request.content)["state"] == "bad"
        payload = {"model": PINNED_MODEL, "usage": {"input_tokens": 40, "output_tokens": 15},
                   "answers": {"check": answer({"C": .0, "A": .1, "B": .9}, "A" if bad else "B")}}
        return httpx.Response(200, json=payload)

    body = {"model": PINNED_MODEL, "state": "ok", "questions": {"check": {"criteria": dict.fromkeys("ABC")}}}
    ledger = Ledger(tmp_path / "ledger.sqlite", .015)
    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        valid = call_v2(client, body, ledger, tmp_path)
        assert valid["valid"] and receipt_probabilities(valid) == {"A": .1, "B": .9, "C": .0}
        assert call_v2(client, body, ledger, tmp_path) == valid
        bad = dict(body, state="bad")
        with pytest.raises(ValueError, match="Invalid paid"):
            call_v2(client, bad, ledger, tmp_path)
        with pytest.raises(ValueError, match="Cached Jev receipt"):
            call_v2(client, bad, ledger, tmp_path)
    assert len(calls) == 2
    stored = [json.loads(path.read_bytes()) for path in tmp_path.glob("*.json")]
    invalid, = [row for row in stored if not row["valid"]]
    assert invalid["answer"]["choice"] == "A" and receipt_probabilities(invalid) is None
    assert valid["usd"] == invalid["usd"] == 40 * (0.042 / 1_000_000)
