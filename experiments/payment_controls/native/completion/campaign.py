"""Combine only disjoint receipt ledgers. Preserve the previous upper bound."""
import json
from decimal import Decimal
from pathlib import Path


HERE = Path(__file__).resolve().parent
UNIT = Decimal("0.000000001")


def read(name):
    return json.loads((HERE / name).read_text(), parse_float=Decimal)


def entry(calls, amount):
    return {"requests": calls, "confirmed_usd": Decimal(amount).quantize(UNIT)}


def collect():
    mail = read("mail_results.json")
    money = read("money_results.json")
    notice = read("other_notice_results.json")
    contrast = read("contrast_results.json")
    vendor = read("vendor_results.json")["eliza"]
    selector = read("selector_results.json")
    direct = read("selector_route_results.json")
    assert all(row["accounting"]["executor_accounting_complete"] for row in mail["cells"].values())
    assert not money["executor_reserve_usd"] and not money["unattributed_ledger_attempts"]
    assert len(notice["ledger"]) == 1 and notice["ledger"][0][0] == "completed"
    assert not contrast["unresolved_reserved_usd"] and not vendor["pending_requests"]
    assert not direct["unsettled"] and not direct["new_jev_usd"] and not selector["jev"]["pending"]
    series = {
        "transfer_amount": {"eliza":entry(money["total_attempts"],money["executor_confirmed_usd"])},
        "notice_amount": {"eliza":entry(mail["total_attempts"],mail["settled_usd"])},
        "notice_type_all_attempts": {"eliza":entry(*notice["ledger"][0][1:])},
        "vendor_status": {"eliza":entry(vendor["requests"],vendor["billed_usd"])},
        "receipt_prompt_contrast": {"jev":entry(contrast["requests"],contrast["cost_usd"])},
    }
    for label, filename in (("onboarding","process_results.json"),("chat_reminder","process_chat_results.json"),
                            ("chat_optional","selector_results.json"),("chat_portal","selector_route_results.json")):
        data = read(filename)
        assert not data.get("unsettled",0)
        rows = data["cases"] if "cases" in data else data["cells"]
        series[label] = {"eliza":entry(sum(row["executor_calls"] for row in rows),data["eliza_usd"])}
    series["chat_optional"]["jev"] = entry(selector["jev"]["requests"], selector["jev"]["cost_usd"])
    prior = read("../expansion/costs.json")["summary"]
    totals = {}
    for provider in ("eliza", "jev"):
        cells = [s[provider] for s in series.values() if provider in s]
        totals[provider] = entry(sum(c["requests"] for c in cells),sum(c["confirmed_usd"] for c in cells))
        upper = Decimal(prior[provider]["cumulative_attributable_upper_usd"])
        totals[provider].update(previous_upper_usd=upper, new_unsettled_usd=0,
                                cumulative_upper_usd=upper+totals[provider]["confirmed_usd"])
    return {"series":series, "totals":totals, "attribution":"Provider receipts by request identity; excludes unrelated activity on the same account."}


if __name__ == "__main__":
    (HERE/"costs.json").write_text(json.dumps(collect(), default=str, indent=2)+"\n")
