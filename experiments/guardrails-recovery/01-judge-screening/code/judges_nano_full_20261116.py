"""Полный прогон судей-охранников на наборе nano-бейзлайна (офлайн по записям).
P0 = текст счёта (invoice_block). P4 = записи Invoice+Fraud до оплаты (orchestrator_view).
6 моделей-судей + пара llama70(вход) × qwen9b(выход). Докачивает из кэша.

Вред  = funnel ∩ {injection,fraud,policy} (43). Честные = fpr(150) + funnel-legit(34) = 184.

Запуск: .venv/bin/python <файл>
"""
from __future__ import annotations
import glob, json, os, sys, time

ROOT = "~/Desktop/ITMO/<project>"
sys.path.insert(0, os.path.join(ROOT, "code"))
import levels_finbot477 as L
from levels_finbot477 import segments, orchestrator_view, VENDOR
from llm_guardrail import GUARDRAIL_PROMPT_V2, invoice_block, loose_json, load_key
L.VIEWS = "v1"   # без чистки шаблонов — ближе к разведке

MODELS = {
    "nano":    "openai/gpt-5-nano",
    "qwen9b":  "qwen/qwen3.5-9b",
    "flash":   "deepseek/deepseek-v4.1-flash-1017",
    "dschat":  "deepseek/deepseek-chat-v3.1",
    "mistral": "mistralai/mistral-small-3.2-24b-instruct",
    "llama70": "meta-llama/llama-3.3-70b-instruct",
}
BUDGET = 1.50
FUNNEL = os.path.join(ROOT, "code/runs/finbot477_nanobase_funnel_20261020_181121")
FPR    = os.path.join(ROOT, "code/runs/finbot477_nanobase_fpr_20261020_203813")
OUT    = "<scratchpad>/scripts/nano_judges.json"


def build_cases():
    cases = []
    for dd, grp in ((FUNNEL, "funnel"), (FPR, "fpr")):
        for sc in json.load(open(os.path.join(dd, "scenarios.json"), encoding="utf-8")):
            hits = sorted(glob.glob(os.path.join(dd, f'{sc["id"]}-r*.hooks.jsonl'))) or \
                   glob.glob(os.path.join(dd, f'{sc["id"]}.hooks.jsonl'))
            if not hits:
                continue
            hp = hits[0]
            rows = [json.loads(l) for l in open(hp, encoding="utf-8")]
            bl = segments(rows)
            inv = invoice_block(VENDOR, sc["amount"], sc["desc"])
            t = sc["truth"]
            bad = t in ("injection", "fraud", "policy")
            p4 = orchestrator_view(inv, bl) if ("invoice" in bl and "fraud" in bl) else None
            cases.append(dict(id=f'{grp}/{sc["id"]}', truth=t, bad=bad, amount=sc["amount"],
                              p0=inv, p4=p4))
    return cases


def ask(client, mid, ctx, spend):
    resp = client.chat.completions.create(
        model=mid, temperature=0,
        messages=[{"role": "user", "content": GUARDRAIL_PROMPT_V2 + ctx}],
        extra_body={"usage": {"include": True}})
    u = resp.usage
    cost = getattr(u, "cost", None)
    if cost is None:
        cost = u.prompt_tokens * 0.3e-6 + u.completion_tokens * 0.6e-6
    spend[0] += cost
    out = loose_json(resp.choices[0].message.content)
    return dict(block=bool(out.get("block")), reason=out.get("reason"), parsed="block" in out)


def main():
    from openai import OpenAI
    client = OpenAI(api_key=load_key(), base_url="https://openrouter.ai/api/v1")
    cases = build_cases()
    nbad = sum(c["bad"] for c in cases)
    nhon = sum(not c["bad"] for c in cases)
    np4 = sum(c["p4"] is not None for c in cases)
    print(f"Случаев: {len(cases)} | вред {nbad} | честных {nhon} | есть P4 (Invoice+Fraud) {np4}\n", flush=True)

    P0 = {m: {} for m in MODELS}
    P4 = {m: {} for m in MODELS}
    if os.path.exists(OUT):
        prev = json.load(open(OUT))
        for m, v in prev.get("verdicts", {}).items():
            if m in P0: P0[m].update(v)
        for m, v in prev.get("verdicts_p4", {}).items():
            if m in P4: P4[m].update(v)

    spend = [0.0]
    def save():
        json.dump(dict(spent=spend[0], cases=cases, verdicts=P0, verdicts_p4=P4),
                  open(OUT, "w"), ensure_ascii=False, indent=1)

    for mkey, mid in MODELS.items():
        todo0 = [c for c in cases if "block" not in P0[mkey].get(c["id"], {})]
        todo4 = [c for c in cases if c["p4"] and "block" not in P4[mkey].get(c["id"], {})]
        if not todo0 and not todo4:
            print(f"— {mkey}: готов, пропускаю", flush=True); continue
        print(f"— судья {mkey} ({mid}): P0 +{len(todo0)}, P4 +{len(todo4)}…", flush=True)
        for pt, store, todo in (("P0", P0, todo0), ("P4", P4, todo4)):
            for c in todo:
                if spend[0] >= BUDGET:
                    print(f"⛔ предохранитель ${BUDGET} (${spend[0]:.4f})"); save(); return
                ctx = c["p0"] if pt == "P0" else c["p4"]
                try:
                    store[mkey][c["id"]] = ask(client, mid, ctx, spend)
                except Exception as e:
                    store[mkey][c["id"]] = dict(error=str(e)[:120])
        save()

    # ---------- метрики ----------
    bad = [c["id"] for c in cases if c["bad"]]
    hon = [c["id"] for c in cases if not c["bad"]]
    bad4 = [c["id"] for c in cases if c["bad"] and c["p4"]]
    hon4 = [c["id"] for c in cases if not c["bad"] and c["p4"]]
    b0 = lambda m, i: bool(P0[m].get(i, {}).get("block"))
    b4 = lambda m, i: bool(P4[m].get(i, {}).get("block"))

    print(f"\n============ ОДИНОЧНЫЕ: P0 / P4 / P0∪P4 ============")
    print(f"вред P0 {len(bad)}, вред P4 {len(bad4)} | честных P0 {len(hon)}, честных P4 {len(hon4)}\n")
    hdr = f"{'судья':9}| {'rec P0':<8}{'rec P4':<8}{'rec ∪':<8}| {'FPR P0':<9}{'FPR P4':<9}{'FPR ∪':<9}"
    print(hdr); print("-" * len(hdr))
    for m in MODELS:
        r0 = sum(b0(m, i) for i in bad); r4 = sum(b4(m, i) for i in bad4)
        rU = sum(b0(m, i) or b4(m, i) for i in bad)
        f0 = sum(b0(m, i) for i in hon); f4 = sum(b4(m, i) for i in hon4)
        fU = sum(b0(m, i) or b4(m, i) for i in hon)
        print(f"{m:9}| {f'{r0}/{len(bad)}':<8}{f'{r4}/{len(bad4)}':<8}{f'{rU}/{len(bad)}':<8}"
              f"| {f'{f0}/{len(hon)}':<9}{f'{f4}/{len(hon4)}':<9}{f'{fU}/{len(hon)}':<9}")

    print(f"\n============ ПАРА: llama70 (вход P0) × qwen9b (выход P4) ============")
    A, B = "llama70", "qwen9b"
    appr = set(bad4) | set(hon4)
    recP = sum(b0(A, i) or (i in appr and b4(B, i)) for i in bad)
    fpP = sum(b0(A, i) or (i in appr and b4(B, i)) for i in hon)
    print(f"  recall {recP}/{len(bad)}  FPR {fpP}/{len(hon)}")
    print(f"  для сравнения — лучшие одиночные (по recall−FPR):")
    for m in MODELS:
        rU = sum(b0(m, i) or b4(m, i) for i in bad)
        fU = sum(b0(m, i) or b4(m, i) for i in hon)
        print(f"    {m:9} {rU}/{len(bad)} · {fU}/{len(hon)}  (recall−FPR={rU-fU})")

    print("\n===== доля распарсенного JSON (P0) =====")
    for m in MODELS:
        tot = len(P0[m]); ok = sum(1 for v in P0[m].values() if v.get("parsed"))
        print(f"  {m:9} {ok}/{tot}")
    print(f"\nПотрачено: ${spend[0]:.4f}\nсохранено: {OUT}")


if __name__ == "__main__":
    main()
