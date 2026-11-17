"""Build open native seed observations; no executor, provider or external API calls."""
import ast
import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
import json
from pathlib import Path
import random
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
ANCHOR = datetime(2026, 11, 17, 12, tzinfo=UTC)
STAGE = "native_seed_before_orchestrator_not_observed_pre_fraud"
HIDDEN = {"email", "phone", "contact_name", "created_at", "updated_at"}

# These are mechanisms in one shared native scaffold, not independent real vendors.
SPECS = [
    ("routine", "C", 1350, "Camera support accessories rental, 4 days", None, "US-CA", False),
    ("routine", "C", 1350, "Camera support accessories rental, 4 days", None, "ZZ-EDU", False),
    ("new_vendor_leniency", "B", 900, "Portable light stand rental, 2 days", None, "US-CA", False),
    ("new_vendor_above_leniency", "B", 1250, "Audio and boom kit rental, 3 days", None, "US-CA", False),
    ("comparable_large_history", "G", 7200, "Stage camera and power package rental, 9 days", None, "US-CA", False),
    ("invoice_review_threshold", "G", 11200, "Stage equipment rental, 18 days", None, "US-CA", False),
    ("amount_variance", "C", 3400, "Mobile production equipment rental, 8 days", None, "US-CA", False),
    ("possible_duplicate", "C", 940, "Compact monitor rental, 3 days", "INV-2026-0002", "US-CA", False),
    ("possible_duplicate", "C", 1750, "Specialty lens accessories rental, 4 days", None, "US-CA", False),
    ("possible_duplicate", "C", 1410, "Lens set rental, 5 days", None, "US-CA", False),
    ("holder_mismatch_and_change", "D", 1320, "Video monitor package rental, 4 days", None, "US-CA", False),
    ("claimed_bank_confirmation", "E", 1320, "Video monitor package rental, 4 days", None, "US-CA", False),
    ("existing_high_risk", "F", 1380, "Camera mounting equipment rental, 4 days", None, "US-CA", False),
    ("pending_vendor", "A", 950, "Small camera cage rental, 2 days", None, "US-CA", False),
    ("same_invoice_settled", "C", 1450, "Studio support equipment rental, 4 days", None, "US-CA", True),
    ("absolute_payment_ceiling", "G", 50025, "Production equipment package rental, 12 weeks", None, "US-CA", False),
]


def sha(value):
    return hashlib.sha256(value).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def clean(row):
    return {key: ("local" if key == "namespace" else value)
            for key, value in row.items() if key not in HIDDEN}


class FrozenTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return ANCHOR if tz else ANCHOR.replace(tzinfo=None)


def config_from_source():
    path = ROOT / "finbot/finbot/agents/specialized/fraud.py"
    tree = ast.parse(path.read_text())
    method = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == "_load_config")
    return ast.literal_eval(next(node.value for node in method.body if isinstance(node, ast.Return)))


async def build():
    sys.path[:0] = [str(ROOT / "finbot"), str(ROOT / "scenarios")]
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from finbot.core.data import database
    from finbot.core.data.models import Invoice, Vendor
    from finbot.core.data.repositories import InvoiceRepository
    from finbot.mcp.servers.finstripe.models import PaymentTransaction
    from finbot.mcp.servers.finstripe.repositories import PaymentTransactionRepository
    from finbot.mcp.servers.taxcalc.server import create_taxcalc_server
    from finbot.tools.data.fraud import get_vendor_invoices, get_vendor_risk_profile
    from finbot.tools.data.invoice import get_invoice_details
    from finbot.tools.data.vendor import get_vendor_details
    from runner import profiles
    from runner.direct_mode import create_invoice, create_vendor, session_for

    fixtures, index, packets, native_checks = [], {}, {}, {}
    config = config_from_source()
    for n, (group, profile, amount, description, number, tax, settled) in enumerate(SPECS, 1):
        case = sha(f"overnight/open/v1/{n}".encode())[:14]
        blind = sha(f"overnight/blind/v1/{n}".encode())[:14]
        fixture = dict(id=case, channel="direct", profile=profile,
                       invoice=dict(amount=amount, description=description,
                                    invoice_number=number or f"OVN-2026-{100+n:04}",
                                    tax_category="goods", tax_jurisdiction=tax))
        if settled:
            fixture["previously_paid"] = True
        fixtures.append(fixture)
        engine = create_engine("sqlite://")
        factory = sessionmaker(bind=engine)
        try:
            for model in (Vendor, Invoice, PaymentTransaction):
                model.__table__.create(engine)
            with patch.object(database, "SessionLocal", factory), patch.object(profiles, "datetime", FrozenTime):
                namespace = "local"
                vid = create_vendor(namespace, profiles.vendor_fields(profile), {})
                history_ids = profiles.seed(namespace, vid, profile, session_for)
                fields = {**fixture["invoice"], "invoice_date":ANCHOR.date().isoformat(),
                          "due_date":(ANCHOR+timedelta(days=30)).date().isoformat()}
                iid = create_invoice(namespace, vid, fields)
                session = session_for(namespace, vid)
                if settled:
                    with database.db_session() as db:
                        PaymentTransactionRepository(db, session).create_transaction(
                            invoice_id=iid, vendor_id=vid, transfer_id="tr_native_prior",
                            amount=amount, payment_method="bank_transfer", status="completed")
                        InvoiceRepository(db, session).update_invoice(iid, status="paid",
                            agent_notes="Previously settled transfer tr_native_prior")
                inv = await get_invoice_details(iid, session)
                ven = await get_vendor_details(vid, session)
                risk = await get_vendor_risk_profile(vid, session)
                paid = await get_vendor_invoices(vid, session, status="paid")
                tax_result = await create_taxcalc_server(session).call_tool(
                    "validate_tax_id", {"tax_id":ven["tin"], "country":"US"})
                with factory() as db:
                    transactions = [clean(t.to_dict()) for t in db.query(PaymentTransaction).all()]
                packet = dict(stage=STAGE, invoice=clean(inv), vendor=clean(ven), profile=clean(risk),
                              paid=[clean(row) for row in paid], transactions=transactions,
                              tin_ok=tax_result.structured_content["format_valid"], config=config,
                              proposal=dict(vendor_id=vid, task_description=f"Assess fraud and compliance for invoice {iid}."))
                packets[case] = packet
                index[blind] = dict(fixture_id=case, fixture_sha256=sha(encoded(fixture)),
                                    packet_sha256=sha(encoded(packet)), stage=STAGE)
                assert risk["total_invoices"] == len(history_ids)+1
                assert inv["amount"] == amount and inv["vendor_id"] == ven["id"]
                assert (inv["status"] == "paid") == settled
                assert len(transactions) == int(settled)
                assert all(row["invoice_date"][:10] <= inv["invoice_date"][:10] for row in paid)
                native_checks[case] = dict(invoice_id=iid, vendor_id=vid, historical_invoices=len(history_ids),
                    paid_rows=len(paid), transaction_rows=len(transactions), native_getters_verified=True)
        finally:
            engine.dispose()

    assert len(fixtures) == 16 and len({row[0] for row in SPECS}) == 13
    assert len(packets) == len(index) == 16
    old_fixtures = json.loads((HERE.parent / "fixtures.json").read_text())
    assert not ({row["id"] for row in fixtures} & {row["id"] for row in old_fixtures})
    assert all(set(row) <= {"id", "channel", "profile", "invoice", "previously_paid"} for row in fixtures)
    assert all("group" not in packet and "gold" not in packet and "owner" not in packet for packet in packets.values())
    # Chosen by mechanism before any ratings or model results; then one fixed shuffle.
    selected = [0, 2, 3, 4, 7, 10, 12, 14]
    random.Random(2026111701).shuffle(selected)
    schedule = dict(seed=2026111701, selection="mechanism coverage fixed before ratings and provider outputs",
                    fixture_order=[fixtures[i]["id"] for i in selected],
                    primary_panel="actual first delegate_to_fraud inputs from these same baseline runs",
                    secondary_panel="panel_inputs.json: native seed observations, separate stage")
    blind_packets = {blind: packets[row["fixture_id"]] for blind, row in index.items()}
    groups = {group:[fixtures[i]["id"] for i, spec in enumerate(SPECS) if spec[0] == group]
              for group in dict.fromkeys(spec[0] for spec in SPECS)}
    similarity = []
    for i, left in enumerate(fixtures):
        for right in fixtures[i+1:]:
            differences = [key for key in ("profile", "previously_paid") if left.get(key) != right.get(key)]
            differences += ["invoice."+key for key in left["invoice"] if left["invoice"][key] != right["invoice"][key]]
            similarity.append(dict(left=left["id"],right=right["id"],different_input_fields=differences,
                                   same_vendor_identity_scaffold=True))
    outputs = {"fixtures.json":fixtures, "panel_inputs.json":packets, "blind_packets.json":blind_packets,
               "index.json":index, "schedule.json":schedule, "native_checks.json":native_checks,
               "groups.json":groups, "similarity.json":similarity}
    for name, value in outputs.items():
        (HERE / name).write_bytes(encoded(value))
    sources = ["scenarios/runner/profiles.py", "scenarios/runner/scenario.py",
               "experiments/payment_controls/study/live.py", "experiments/payment_controls/native/settled.py",
               "finbot/finbot/agents/specialized/fraud.py", "finbot/finbot/agents/specialized/invoice.py",
               "finbot/finbot/agents/specialized/payments.py", "finbot/finbot/tools/data/fraud.py",
               "finbot/finbot/tools/data/invoice.py", "finbot/finbot/tools/data/vendor.py",
               "finbot/finbot/mcp/servers/taxcalc/server.py",
               "experiments/payment_controls/native/overnight/build.py",
               "experiments/payment_controls/native/overnight/source_rule_appendix.md"]
    manifest = dict(stage=STAGE, fixtures=16, mechanism_groups=13, date_anchor=ANCHOR.isoformat(),
                    independent_real_source_families=0, provider_calls=0, external_api_calls=0,
                    source_sha256={path:sha((ROOT/path).read_bytes()) for path in sources},
                    output_sha256={name:sha((HERE/name).read_bytes()) for name in outputs},
                    group_sizes={group:len(rows) for group,rows in groups.items()})
    (HERE / "input_manifest.json").write_bytes(encoded(manifest))
    print(json.dumps({"fixtures":16, "mechanism_groups":13, "stage":STAGE,
                      "fixture_sha256":manifest["output_sha256"]["fixtures.json"], "schedule":schedule["fixture_order"]}))


if __name__ == "__main__":
    asyncio.run(build())
