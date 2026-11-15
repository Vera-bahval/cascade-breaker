"""Unpaid physical linkage check. Does not establish who authorized the commercial terms."""
import argparse
import csv
import json
import os
import sys
import tempfile
from pathlib import Path

from .live import ROOT
from .scene import Scene


def check(corpus):
    meta={r["case"]:r for r in map(json.loads,(corpus/"scene-en.private.jsonl").read_text().splitlines())}
    inputs={r["case"]:r for r in map(json.loads,(corpus/"inputs.jsonl").read_text().splitlines())}
    if inputs.keys()!=meta.keys():raise ValueError("Scene and document IDs differ")
    sys.path[:0]=[str(ROOT/"scenarios"),str(ROOT/"finbot")]
    with tempfile.TemporaryDirectory() as scratch:
        os.environ["DATABASE_URL"]="sqlite:///"+scratch+"/fixture.db"
        os.chdir(ROOT/"finbot")
        from finbot.main import app
        from finbot.core.data.database import create_tables
        from finbot.core.data.repositories import InvoiceRepository
        from finbot.probe.guards.workflow import workflow_snapshot
        from runner import case_direct, direct_mode, profiles
        from runner.scenario import invoice_fields
        create_tables()
        functions=[(profiles,"vendor_fields"),(profiles,"history_invoices"),(InvoiceRepository,"create_invoice_for_current_vendor"),
                   (case_direct,"create_invoice"),(case_direct,"_orchestrate")]
        originals=[getattr(mod,name) for mod,name in functions]
        for key,doc in inputs.items():
            scene=Scene(meta[key],doc)
            if meta[key]["scene_status"]!="resolved":
                yield {"case":key,"scene":meta[key]["scene_status"],"linked":False}
                continue
            try:
                scene.install()
                namespace="fixture-"+key
                vid=direct_mode.create_vendor(namespace,profiles.vendor_fields("C"),{})
                profiles.seed(namespace,vid,"C",direct_mode.session_for)
                fields=invoice_fields({"amount":480,"description":scene.description,"tax_jurisdiction":"US-CA","tax_category":"goods"},scene.number)
                iid=case_direct.create_invoice(namespace,vid,fields)
                session=direct_mode.session_for(namespace,vid)
                snap=workflow_snapshot(session,{"invoice_id":iid})
                inv=snap["invoice"]
                assert snap["vendor"]["services"]==", ".join(meta[key]["vendor_services"])
                assert inv["amount"]==480 and inv["description"]==scene.description
                assert scene.ref["sha256"] in inv["agent_notes"] and scene.read(session,inv)==scene.document
                try:
                    scene.read(session,{**inv,"attachments":[]})
                except ValueError:
                    pass
                else:
                    raise AssertionError("Detached evidence accepted")
                yield {"case":key,"scene":"resolved","linked":True}
            finally:
                for (mod,name),fn in zip(functions,originals):setattr(mod,name,fn)


if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("corpus",type=Path)
    folder=cli.parse_args().corpus.resolve()
    rows=list(check(folder))
    with (folder/"scene-linkage.private.csv").open("w") as stream:
        w=csv.DictWriter(stream,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    print(len(rows),sum(r["linked"] for r in rows))
