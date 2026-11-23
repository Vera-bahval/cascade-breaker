"""Resume unstarted, frozen requests after the transport incident; keep the original reserve and missing answer."""
from concurrent.futures import ThreadPoolExecutor
import fcntl
from itertools import batched

import httpx
from . import report, run


def dispatch():
    original = run.original
    folder = run.PRIVATE
    manifest = run.read(run.HERE / "freeze.json")
    expected = original.digest((run.HERE / "freeze.json").read_bytes())
    if run.read(folder/"release.json") != dict(reviewer="root", approved=True, freeze_sha256=expected):
        raise ValueError("Unreleased freeze")
    if manifest["code_sha256"] != original.digest((run.HERE/"run.py").read_bytes()):
        raise ValueError("Changed experiment code")
    meta = original.eliza.metadata()
    model, = meta["model"]["data"]
    remaining = meta["remaining"]
    if (model["id"] != original.eliza.MODEL or model["disabled"] or model["endpoint"] != original.ENDPOINT or
        remaining["monthly_usd"] < run.E_CAP or any(model["prices"][k] > v for k,v in original.PRICES.items())):
        raise ValueError("Original dependency, quota or tariff changed")
    limit, = [r["usage"]["cost"] for x in meta["quotas"]["quotas"]["external"]["limits"] if x["name"]=="all"
              for r in x["limits"] if r["type"]=="daily"]
    if limit != -1 and remaining["daily_usd"] < run.E_CAP:
        raise ValueError("Daily quota insufficient")
    with (folder/"eliza.lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        attempted=report.all_eliza_billing()
        if any(status not in {"complete","pending"} for _,_,status in attempted.values()):
            raise ValueError("Unexpected historical account state")
        prior_exposure=sum(reserve if cost is None else cost for reserve,cost,status in attempted.values())
        available=run.E_CAP-prior_exposure
        order=sorted(manifest["rows"],key=lambda r:original.digest(run.jev.wire(["guard-pair-v1",r["id"]])))
        sequence=[(r,"native_source") for r in order]
        sequence += [(r,a) for r in order for a in run.PROMPTS[2:] if (r["source"],a)!=("historical","short_choice_32")]
        sequence += [(r,"native_legacy") for r in order]
        unstarted=[(r,a) for r,a in sequence if run.key(r,a) not in attempted]
        if not unstarted or available <= 0:
            return
        number=len(attempted)
        wave=folder/f"eliza-wave-{number}.sqlite"
        ledger=original.eliza.Ledger(wave,available)
        original.persist_once(folder/f"wave-{number}.json",run.jev.wire({"frozen":expected,"attempted":number,
                              "unstarted":len(unstarted),"prior_exposure":prior_exposure,"wave_cap":available}))
        headers={"Authorization":"OAuth "+original.eliza.token(),"X-Retries":"1","Content-Type":"application/json","X-Request-Timeout":"60s"}
        original.PRIVATE,original.reserve=folder,run.reserve
        with httpx.Client(headers=headers,timeout=80,trust_env=False,follow_redirects=False) as client, ThreadPoolExecutor(8) as executor:
            for batch in batched(unstarted,8):
                items=[(run.key(r,a),run.request_bytes(r,a)) for r,a in batch]
                balance=ledger.summary()
                if balance["cost_usd"]+balance["unresolved_reserved_usd"]+sum(run.reserve(b) for _,b in items)>available:
                    break
                tasks=[executor.submit(original.request,client,ledger,{"id":k},b) for k,b in items]
                if not all([f.result() for f in tasks]): break
        print(ledger.summary())


if __name__=="__main__":
    dispatch()
