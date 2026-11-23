"""Check joins across the policy revision, cost ledgers, matched continuations and final reports."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / name).read_bytes())


def rows(name):
    return [json.loads(line) for line in (ROOT / name).read_text().splitlines()]


def check():
    old = read("review/results.json")
    revised = read("correction/policy/results.json")
    overlay = rows("correction/policy/assignment-overlay.jsonl")
    assert len({r['assignment'] for r in overlay}) == len(overlay) == 1105
    assert len({r['family'] for r in overlay}) == 221
    assert all({r["arm"] for r in overlay if r["family"] == family} == set("ABCDE")
               for family in {r["family"] for r in overlay})
    census = rows("correction/policy/mechanical-census.jsonl")
    assert sum(r["completed_db_transfers"] for r in census) == sum(len(r["completed_receipt_matches"]) for r in census) == 932
    assert {r["assignment"] for r in census} == {r["assignment"] for r in overlay}
    for a in "ABCDE":
        subset = [r for r in overlay if r["arm"] == a]
        assert sum(r["financial"] == "VIOLATED" for r in subset) == revised["arms"][a]["outcomes"]["financial"]["adverse"]
        assert sum(r["prior_gold"]["financial"] == "VIOLATED" for r in subset) == old["arms"][a]["outcomes"]["financial"]["adverse"]
    rr = read("correction/design/repeats.json")
    assert len(rr["assignments"]) == 200 and len(set(r["family"] for r in rr["assignments"])) == 4
    first = read("correction/guards/primary-results.json")
    final = read("correction/guards/results.json")
    assert first["freeze_sha256"] == final["freeze_sha256"] == sha256((ROOT/"correction/guards/freeze.json").read_bytes()).hexdigest()
    assert first["gold_sha256"] == final["gold_sha256"]
    assert first["gold_sha256"]["modern"] == sha256((ROOT/"correction/policy/modern-a-actions.release.jsonl").read_bytes()).hexdigest()
    assert len(first["rows"]) == len(final["rows"]) == len({r["id"] for r in final["rows"]}) == 516
    for a,b in zip(first["rows"],final["rows"],strict=True):
        assert all(a[k] == b[k] for k in ("id","gold","jev","native_source"))
        assert a["jev"]["status"] == a["native_source"]["status"] == "valid"
    for key,limit in (("eliza",2),("jev",.50)):
        bill=final["billing"][key]
        assert bill["settled_usd"] + bill["unresolved_reserved_usd"] <= limit
    repeat = read("correction/guards/technical-repeat.json")
    original = next(r for r in final["rows"] if r["id"] == repeat["id"])
    assert original[repeat["arm"]]["status"] == "technical" and original["wires"][repeat["arm"]] == repeat["wire_sha256"]
    assert repeat["repeat"]["status"] == "valid"
    assert sum(final["billing"]["eliza"][k] + repeat["repeat_billing"][k] for k in ("settled_usd","unresolved_reserved_usd")) <= 2
    groups=read("correction/continuations/results.json")
    assert groups["settled_eliza_usd"] + groups["open_eliza_reserve_usd"] <= 5
    arms=[r for group in groups["results"].values() for r in group["arms"].values()]
    assert len(arms)==12 and all(r["status"]=="TERMINAL" for r in arms)
    assert sum(len(r["completed_transfer_evidence"]) for r in arms)==3
    assert sum(len(r["invoice_bound_vendor_notice_receipts"]) for r in arms)==12
    assert len({g['assignment'] for g in groups['results'].values()})==4
    html=(ROOT/'FINBOT_TEAM.html').read_text()
    dashboard=json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>',html,re.S)[1])
    assert len(dashboard['readytable'])==10 and len(dashboard['policytable'])==6
    assert dashboard['audit']==read('correction_registry.json')
    assert all(dashboard[k] for k in ['causalresult','guardlead','cost','limits','guardresult'])
    print('Verified 1105 initial assignments, 200 repeated-family executions (8 also primary), 932 transfers, 516 model pairs and 12 continuations.')


if __name__ == '__main__':
    check()
