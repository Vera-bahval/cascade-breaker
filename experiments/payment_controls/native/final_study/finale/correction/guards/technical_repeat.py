"""Repeat the one unanswered formatting-control request; keep it separate from first-assignment metrics."""
import fcntl
import json
from pathlib import Path
import httpx
from . import report, run


def main():
    folder = run.PRIVATE
    with (folder/"eliza.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        freeze=run.read(run.HERE/"freeze.json")
        assert run.read(folder/"release.json")==dict(reviewer="root",approved=True,freeze_sha256=run.original.digest((run.HERE/"freeze.json").read_bytes()))
        all_first=report.all_eliza_billing()
        unresolved=[k for k,(_,cost,_) in all_first.items() if cost is None]
        if len(unresolved)!=1:
            raise ValueError("The technical-repeat protocol is restricted to one unanswered request")
        ident,=unresolved
        row,= [r for r in freeze["rows"] if ident==run.key(r,"short_choice")]
        payload=run.request_bytes(row,"short_choice")
        prior=folder/(ident+".http.json")
        assert json.loads(prior.read_bytes()).get("transport_error")
        directory=folder/"technical-repeat"
        directory.mkdir(exist_ok=True,mode=0o700)
        spent=sum(reserve if cost is None else cost for reserve,cost,status in all_first.values())
        budget=min(.01,run.E_CAP-spent)
        assert run.reserve(payload)<=budget
        ledger=run.original.eliza.Ledger(directory/"ledger.sqlite",budget)
        meta=run.original.eliza.metadata()
        model,=meta["model"]["data"]
        assert model["id"]==run.original.eliza.MODEL and not model['disabled'] and model['endpoint']==run.original.ENDPOINT
        assert meta["remaining"]["monthly_usd"]>=budget and all(model["prices"][k]<=v for k,v in run.original.PRICES.items())
        run.original.PRIVATE=directory
        run.original.reserve=run.reserve
        run.original.persist_once(directory/(ident+".request"),payload)
        if not ledger.summary()["requests"]:
            with httpx.Client(headers={"Authorization":"OAuth "+run.original.eliza.token(),"X-Retries":"1","Content-Type":"application/json",
                                       "X-Request-Timeout":"60s"},timeout=80,trust_env=False,follow_redirects=False) as client:
                run.original.request(client,ledger,{"id":ident},payload)
        first_dir=run.PRIVATE
        run.PRIVATE=directory
        try:
            val=report.eliza_row(row,"short_choice",run.jev.billing_entries(ledger.path),{})
        finally:
            run.PRIVATE=first_dir
        receipt={"id":row['id'],"source":row['source'],"point":row['point'],"arm":"short_choice","wire_sha256":row['wires']['short_choice'],
                 "original_transport":json.loads(prior.read_bytes()),"first_reserved_usd":all_first[ident][0],
                 "repeat":val,"repeat_billing":report.money(run.jev.billing_entries(ledger.path))}
        (run.HERE/"technical-repeat.json").write_text(json.dumps(receipt,indent=2)+"\n")


if __name__=="__main__":
    main()
