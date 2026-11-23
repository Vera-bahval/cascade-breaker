"""Apply native FinMail to four copies of one archived pre-call evidence state."""
import asyncio
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from .mail_binding import HERE, TARGET, binding, completed, local_vendor, sha


async def matched(raw, trace, original, lookup, action, written, wrong, right, *, saved_link=None):
    from fastmcp import Client
    from finbot.main import app  # register model metadata
    from finbot.core.data import database
    from finbot.mcp.servers.finmail.server import create_finmail_server
    from runner.direct_mode import session_for

    prefix = [s for s in trace["steps"] if s["seq"] < action]
    steps = {s["seq"]: s for s in trace["steps"]}
    draft = steps[action]["arguments"]
    assert steps[action - 1]["output"]["tool_calls"][0]["arguments"] == draft
    assert steps[lookup]["output"]["error"] == "Invoice not found"
    assert steps[written]["output"]["sent"] is True
    if saved_link is None:
        assert steps[written]["arguments"]["related_invoice_id"] == 0
        assert "FOREIGN KEY constraint failed" in steps[action]["output"]["error"]
    receipt, = completed(prefix)
    iid = receipt["invoice_id"]
    vendor = local_vendor(original, iid)
    with TemporaryDirectory(prefix="finmail-prefix-") as directory:
        state = Path(directory) / "source.sqlite"
        with sqlite3.connect(original.as_uri() + "?mode=ro", uri=True) as source:
            with sqlite3.connect(state) as dest:
                source.backup(dest)
        with sqlite3.connect(state) as db:
            namespace, number, vendor_id, amount = db.execute(
                "select namespace,invoice_number,vendor_id,amount from invoices where id=?", (iid,)
            ).fetchone()
            tx, = db.execute("select transfer_id,invoice_id,vendor_id,amount,status from payment_transactions "
                             "where namespace=? and invoice_id=?", (namespace, iid)).fetchall()
            assert tx == (receipt["transfer_id"], iid, vendor_id, amount, "completed")
            recovered, = db.execute(
                "select id,subject,body,related_invoice_id,vendor_id from emails "
                "where namespace=? and subject=? and body=?", (namespace, draft["subject"], draft["body"])
            ).fetchall()
            assert recovered[1:] == (draft["subject"], draft["body"], saved_link, vendor_id)
            assert iid == right and draft["related_invoice_id"] == wrong and receipt["invoice_reference"] == number
            assert not db.execute("select id from invoices where id=?", (wrong,)).fetchone()
            db.execute("delete from emails where id=?", (recovered[0],))
            prior_emails = db.execute("select id,subject from emails where namespace=?", (namespace,)).fetchall()
            db.commit()
            assert db.execute("pragma wal_checkpoint(truncate)").fetchone()[0] == 0
        state_sha = sha(state.read_bytes())
        cells = []
        for condition, provided, enforce in [
            ("wrong", wrong, False), ("repaired", wrong, True),
            ("correct", iid, False), ("omitted", None, False),
        ]:
            file = Path(directory) / f"{condition}.sqlite"
            file.write_bytes(state.read_bytes())
            assert sha(file.read_bytes()) == state_sha
            args = dict(draft)
            if provided is None:
                del args["related_invoice_id"]
            else:
                args["related_invoice_id"] = provided
            verdict, canonical = binding(args, [receipt], vendor)
            if enforce and verdict == "REPAIR":
                args["related_invoice_id"] = canonical
            engine = create_engine(f"sqlite:///{file}")
            @event.listens_for(engine, "connect")
            def foreign_keys(connection, _record):
                connection.execute("PRAGMA foreign_keys=ON")

            try:
                with patch.object(database, "SessionLocal", sessionmaker(bind=engine)):
                    mail = create_finmail_server(session_for(namespace, vendor_id))
                    async with Client(mail) as client:
                        result = await client.call_tool("send_email", args)
                assert result.data["delivery_count"] == 1
                fk_failed = False
            except Exception as exc:
                if "FOREIGN KEY constraint failed" not in str(exc):
                    raise
                fk_failed = True
            finally:
                engine.dispose()
            with sqlite3.connect(file) as db:
                emails = db.execute(
                    "select related_invoice_id,vendor_id,subject,body from emails where namespace=? and subject=?",
                    (namespace, draft["subject"])
                ).fetchall()
                assert db.execute("select id,subject from emails where namespace=? and subject<>?",
                                  (namespace, draft["subject"])).fetchall() == prior_emails
                assert [tx] == db.execute("select transfer_id,invoice_id,vendor_id,amount,status from payment_transactions "
                                          "where namespace=? and invoice_id=?", (namespace, iid)).fetchall()
            expected = [] if condition == "wrong" else [
                (None if condition == "omitted" else iid, vendor_id, draft["subject"], draft["body"])
            ]
            assert emails == expected and fk_failed == (condition == "wrong"), (condition, fk_failed, len(emails))
            cells.append(dict(condition=condition, verdict=verdict, original_arg=provided,
                              final_arg=args.get("related_invoice_id"), delivered=len(emails),
                              delivered_link=emails[0][0] if emails else None, foreign_key_rejected=fk_failed))
    return dict(episode_sha256=sha(raw), prefix_sha256=sha(json.dumps(prefix, sort_keys=True).encode()),
                last_prefix_seq=prefix[-1]["seq"], first_action_seq=action, source_state_sha256=state_sha,
                removed_delivered_email_seq=written, invoice_number=number, transfer_amount=amount, cells=cells)


async def main():
    from .mail_binding import RUNTIME, ROOT

    checkpoint = (TARGET / "episode.json").read_bytes()
    trace, = json.loads(checkpoint)["traces"].values()
    result = {"checkpoint": await matched(checkpoint, trace, TARGET / "finbot.db", 58, 60, 62, 1000, 6)}
    key = "onboarding-m1-rules-6ef0ae19886c22"
    source = json.loads((HERE / "audit_observed_steps.json").read_bytes())[key]
    native = (ROOT / source["raw_trace"]).read_bytes()
    assert sha(native) == source["trace_sha256"]
    db = RUNTIME / source["dataset"] / key / "finbot.db"
    result["native"] = await matched(native, json.loads(native), db, 52, 58, 60, 35, 1)
    from .binding_live import LIVE

    folder = LIVE / "guard"
    prospective = (folder / "direct-trace.json").read_bytes()
    trace, = json.loads(prospective).values()
    notice, = [s for s in trace["steps"] if s.get("name") == "finmail__send_email"]
    wrong = notice["arguments"]["related_invoice_id"]
    last_lookup = next(s for s in trace["steps"] if s.get("name") == "get_invoice_details"
                       and s.get("arguments", {}).get("invoice_id") == wrong)
    event, = json.loads((folder / "binding-events.json").read_bytes())
    assert event["verdict"] == "REPAIR" and event["supplied"] == wrong and event["sent"]
    result["prospective_posthoc"] = await matched(prospective, trace, folder / "finbot.db",
        last_lookup["seq"], notice["seq"], notice["seq"], wrong, event["actual"], saved_link=event["actual"])
    (HERE / "binding_matched.json").write_text(json.dumps(result, indent=2) + "\n")
    print({k: v["cells"] for k, v in result.items()})


if __name__ == "__main__":
    asyncio.run(main())
