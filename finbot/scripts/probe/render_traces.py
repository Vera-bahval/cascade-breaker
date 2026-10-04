"""Render recorded probe runs into one self-contained HTML viewer per batch.

The page lists the runs (filter by set, outcome, blocks, text) and shows for
the selected run: outcome and database before/after, a matrix of verifier
verdicts per control point, the P7 annotation, and the full step timeline:
delegations with the enriched task text, every LLM call with its new input
messages and output, every tool call with arguments and result, injections
and guard verdicts. Long LLM histories are stored as deltas against the
previous call of the same agent, so the page stays small.

Usage (from repos/finbot-ctf):
    uv run python scripts/probe/render_traces.py runs/shadow-main.jsonl
Writes experiments/finbot-probe/viewer/<name>.html; open it in a browser.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# pylint: disable=wrong-import-position
# ruff: noqa: E402
from common import EXPERIMENT_DIR


def _compress_llm(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    last: dict[str, list] = {}
    out = []
    for s in steps:
        s = dict(s)
        if s["kind"] == "llm":
            msgs = s.pop("messages") or []
            prev = last.get(s["agent"])
            if prev is not None and len(prev) <= len(msgs) and msgs[: len(prev)] == prev:
                s["new_messages"] = msgs[len(prev):]
                s["history_len"] = len(prev)
            else:
                s["new_messages"] = msgs
                s["history_len"] = 0
            last[s["agent"]] = msgs
        out.append(s)
    return out


def _paid(rec: dict[str, Any]) -> bool:
    return any(t["status"] == "completed" for t in rec["db_final"]["transactions"])


def _prepare(rec: dict[str, Any]) -> dict[str, Any]:
    blocks = sorted({
        f"{s['family']}:{s['verifier']}" for s in rec["steps"]
        if s["kind"] == "guard" and s["decision"] == "block"
    })
    return {
        "meta": {
            "run_id": rec["run_id"], "key": rec["key"], "set": rec["set_name"],
            "case": rec["case_id"], "replicate": rec["replicate"], "split": rec["split"],
            "injection": ".".join(rec["injection"]) if rec["injection"] else None,
            "injection_applied": rec.get("injection_applied"),
            "mode": rec["mode"], "enforce": rec.get("enforce"),
            "paid": _paid(rec), "status": rec["db_final"]["invoice"]["status"],
            "amount": rec["db_initial"]["invoice"]["amount"],
            "cost": round(rec["usage"]["cost_usd"], 5), "wall_s": rec["wall_s"],
            "llm_calls": rec["usage"]["llm_calls"], "stopped_by": rec.get("stopped_by"),
            "error": rec.get("error"), "blocks": blocks,
            "orchestrator_summary": rec.get("orchestrator_summary"),
            "pr477": rec.get("pr477_cascade_type"), "git_sha": rec.get("git_sha"),
        },
        "db_initial": rec["db_initial"],
        "db_final": rec["db_final"],
        "p7": rec.get("p7"),
        "steps": _compress_llm(rec["steps"]),
    }


PAGE = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>FinBot Probe Traces</title>
<style>
:root{--bg:#fafaf9;--panel:#fff;--ink:#1c1917;--mute:#78716c;--line:#e7e5e4;--acc:#2563eb;
--ok:#15803d;--okbg:#dcfce7;--bad:#b91c1c;--badbg:#fee2e2;--warn:#a16207;--warnbg:#fef9c3;--code:#f5f5f4}
@media (prefers-color-scheme:dark){:root{--bg:#1c1917;--panel:#262220;--ink:#f5f5f4;--mute:#a8a29e;
--line:#3f3a37;--acc:#60a5fa;--ok:#4ade80;--okbg:#14532d;--bad:#f87171;--badbg:#7f1d1d;--warn:#facc15;
--warnbg:#713f12;--code:#1f1b19}}
*{box-sizing:border-box}body{margin:0;font:14px/1.45 system-ui,sans-serif;background:var(--bg);color:var(--ink)}
#app{display:grid;grid-template-columns:360px 1fr;height:100vh}
#side{border-right:1px solid var(--line);display:flex;flex-direction:column;min-height:0;background:var(--panel)}
#filters{padding:10px;border-bottom:1px solid var(--line);display:grid;gap:6px}
#filters input,#filters select{width:100%;padding:5px;background:var(--bg);color:var(--ink);border:1px solid var(--line);border-radius:4px}
#list{overflow:auto;flex:1}
.item{padding:7px 10px;border-bottom:1px solid var(--line);cursor:pointer}
.item:hover{background:var(--bg)}.item.sel{outline:2px solid var(--acc);outline-offset:-2px}
.item .k{font-weight:600;font-size:13px;word-break:break-all}.item .s{color:var(--mute);font-size:12px}
#main{overflow:auto;padding:16px 20px}
h2{margin:0 0 6px;font-size:17px;word-break:break-all}h3{margin:18px 0 6px;font-size:14px}
.pill{display:inline-block;padding:1px 7px;border-radius:9px;font-size:12px;margin:0 4px 3px 0;background:var(--code)}
.paid{background:var(--badbg);color:var(--bad)}.unpaid{background:var(--okbg);color:var(--ok)}
.allow{background:var(--okbg);color:var(--ok)}.block{background:var(--badbg);color:var(--bad)}
.inj{background:var(--warnbg);color:var(--warn)}
table{border-collapse:collapse;font-size:12px}td,th{border:1px solid var(--line);padding:3px 6px;text-align:left;vertical-align:top}
.cell{cursor:help}
pre{background:var(--code);padding:8px;border-radius:4px;white-space:pre-wrap;word-break:break-word;margin:4px 0;font-size:12px;max-height:420px;overflow:auto}
.step{border:1px solid var(--line);border-radius:5px;margin:5px 0;background:var(--panel)}
.step>summary{padding:5px 8px;cursor:pointer;list-style:none;display:flex;gap:8px;align-items:baseline}
.step>summary::-webkit-details-marker{display:none}
.step .t{color:var(--mute);font-variant-numeric:tabular-nums;min-width:62px;font-size:12px}
.step .kind{font-size:11px;font-weight:700;text-transform:uppercase;min-width:84px}
.step .body{padding:4px 10px 8px}
.k-llm .kind{color:var(--acc)}.k-tool .kind{color:var(--ok)}.k-delegation .kind{color:#9333ea}
.k-injection{border-color:var(--warn)}.k-injection .kind{color:var(--warn)}.k-guard .kind,.k-guard_context .kind{color:var(--mute)}
.k-summary .kind{color:#0891b2}.msg{border-left:3px solid var(--line);padding-left:8px;margin:6px 0}
.role{font-size:11px;color:var(--mute);text-transform:uppercase}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
label.chk{display:flex;gap:6px;align-items:center;font-size:13px}
@media (max-width:800px){#app{grid-template-columns:1fr;height:auto}#side{max-height:45vh}.grid2{grid-template-columns:1fr}}
</style></head><body>
<div id="app"><div id="side"><div id="filters">
<div><b id="title"></b> <span id="count" class="pill"></span></div>
<input id="q" placeholder="Поиск: сценарий, run_id, текст">
<select id="set"><option value="">Все наборы</option></select>
<select id="paid"><option value="">Любой исход</option><option value="1">Перевод был</option><option value="0">Перевода не было</option></select>
<label class="chk"><input type="checkbox" id="blocked"> Только с block</label>
<label class="chk"><input type="checkbox" id="hideguards"> Скрыть шаги проверок в ленте</label>
</div><div id="list"></div></div><div id="main"><p>Выберите прогон слева.</p></div></div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const runs=D.runs;const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
const J=o=>esc(JSON.stringify(o,null,2));
$('#title').textContent=D.label;
[...new Set(runs.map(r=>r.meta.set))].forEach(s=>{const o=document.createElement('option');o.value=s;o.textContent=s;$('#set').append(o)});
let sel=null;
function filtered(){const q=$('#q').value.toLowerCase(),st=$('#set').value,pd=$('#paid').value,bl=$('#blocked').checked;
 return runs.filter(r=>{const m=r.meta;if(st&&m.set!==st)return false;if(pd&&String(+m.paid)!==pd)return false;
  if(bl&&!m.blocks.length)return false;if(q&&!(m.key+' '+m.run_id+' '+JSON.stringify(r.steps)).toLowerCase().includes(q))return false;return true})}
function list(){const f=filtered();$('#count').textContent=f.length+' / '+runs.length;
 $('#list').innerHTML=f.map(r=>{const m=r.meta;return `<div class="item ${sel===m.run_id?'sel':''}" data-id="${m.run_id}">
 <div class="k">${esc(m.case)} ${m.injection?`<span class="pill inj">${esc(m.injection)}</span>`:''}</div>
 <div class="s">${esc(m.set)} · r${m.replicate} · ${m.split} · ${esc(m.mode)} · <span class="pill ${m.paid?'paid':'unpaid'}">${m.paid?'перевод':'нет перевода'}</span>${esc(m.status)} · block ${m.blocks.length}</div></div>`}).join('');
 document.querySelectorAll('.item').forEach(el=>el.onclick=()=>{sel=el.dataset.id;list();show(runs.find(r=>r.meta.run_id===sel))})}
['#q','#set','#paid','#blocked'].forEach(s=>$(s).addEventListener('input',list));
$('#hideguards').addEventListener('input',()=>sel&&show(runs.find(r=>r.meta.run_id===sel)));
function matrix(r){const g=r.steps.filter(s=>s.kind==='guard');if(!g.length)return '<p class="s">Проверки не запускались.</p>';
 const pts=[...new Set(g.map(s=>s.point+'#'+s.context_seq))],vs=[...new Set(g.map(s=>s.verifier))].sort();
 return `<table><tr><th>Точка</th>${vs.map(v=>`<th>${v}</th>`).join('')}</tr>`+pts.map(p=>{const [pt,seq]=p.split('#');
 return `<tr><td>${esc(pt)}</td>`+vs.map(v=>{const s=g.find(x=>x.point===pt&&String(x.context_seq)===seq&&x.verifier===v);
 return s?`<td class="cell ${s.decision}" title="${esc(s.reason)}">${s.decision} <span class="s">${Math.round(s.latency_ms)}ms</span></td>`:'<td></td>'}).join('')+'</tr>'}).join('')+'</table>'}
function msg(m){if(m.type==='function_call')return `<div class="msg"><div class="role">function_call ${esc(m.name)}</div><pre>${esc(m.arguments)}</pre></div>`;
 if(m.type==='function_call_output')return `<div class="msg"><div class="role">function_call_output</div><pre>${esc(m.output)}</pre></div>`;
 const c=typeof m.content==='string'?m.content:JSON.stringify(m.content,null,2);
 const long=c.length>1500&&m.role==='system';
 return `<div class="msg"><div class="role">${esc(m.role)}</div>${long?`<details><summary>${c.length} символов</summary><pre>${esc(c)}</pre></details>`:`<pre>${esc(c)}</pre>`}</div>`}
function stepHtml(s){let head='',body='';
 if(s.kind==='llm'){head=`${esc(s.agent)} → ${s.output&&s.output.tool_calls&&s.output.tool_calls.length?s.output.tool_calls.map(c=>esc(c.name)).join(', '):'текст'} <span class="s">${Math.round(s.duration_ms)}ms · in ${s.usage?.input_tokens??'?'} / out ${s.usage?.output_tokens??'?'}</span>`;
  body=`<div class="s">История: ${s.history_len} сообщений выше (не повторяются), новых: ${s.new_messages.length}. Модель ${esc(s.served_model||s.model)}, T=${s.temperature}. Инструменты: ${esc(s.tools.join(', '))}</div>`+s.new_messages.map(msg).join('')+
  `<div class="msg"><div class="role">ответ модели</div><pre>${esc(s.output?.content||'')}</pre>${(s.output?.tool_calls||[]).map(c=>`<pre>${esc(c.name)}(${J(c.arguments)})</pre>`).join('')}</div>`+(s.error?`<pre class="block">${esc(s.error)}</pre>`:'')}
 else if(s.kind==='tool'){head=`${esc(s.agent)}.<b>${esc(s.name)}</b> ${s.error?'<span class="pill block">ошибка</span>':''}<span class="s">${Math.round(s.duration_ms)}ms</span>`;
  body=`<div class="role">аргументы</div><pre>${J(s.arguments)}</pre><div class="role">результат</div><pre>${s.error?esc(s.error):J(s.output)}</pre>`}
 else if(s.kind==='delegation'){head=`оркестратор → <b>${esc(s.target)}</b>`;body=`<div class="role">task_description от оркестратора</div><pre>${esc(s.task_description)}</pre><div class="role">что получил агент (с накопленным контекстом)</div><pre>${esc(s.enriched_task)}</pre>`}
 else if(s.kind==='summary'){head=`${esc(s.agent)} [${esc(s.task_status)}]: ${esc((s.task_summary||'').slice(0,140))}`;body=`<pre>${esc(s.task_summary)}</pre>`}
 else if(s.kind==='injection'){head=`<b>${esc(s.node)}.${esc(s.fault)}</b>`;body=`<div class="role">до</div><pre>${esc(s.before)}</pre><div class="role">после</div><pre>${esc(s.after)}</pre>`}
 else if(s.kind==='guard_context'){head=`${esc(s.point)} <span class="s">пауза ${Math.round(s.pause_ms)}ms</span>`;body=`<div class="role">payload</div><pre>${J(s.payload)}</pre><div class="role">снимок БД</div><pre>${J(s.db_snapshot)}</pre>`}
 else if(s.kind==='guard'){head=`${esc(s.point)} ${esc(s.verifier)} <span class="pill ${s.decision}">${s.decision}</span> <span class="s">${Math.round(s.latency_ms)}ms</span>`;body=`<pre>${esc(s.reason)}</pre>`}
 else {head=esc(s.kind);body=`<pre>${J(s)}</pre>`}
 return `<details class="step k-${s.kind}"><summary><span class="t">${(s.t_ms/1000).toFixed(1)}s</span><span class="kind">${s.kind}</span><span>${head}</span></summary><div class="body">${body}</div></details>`}
function show(r){const m=r.meta,hide=$('#hideguards').checked;
 const steps=r.steps.filter(s=>!(hide&&(s.kind==='guard'||s.kind==='guard_context')));
 $('#main').innerHTML=`<h2>${esc(m.key)}</h2>
 <div><span class="pill ${m.paid?'paid':'unpaid'}">${m.paid?'деньги переведены':'перевода нет'}</span><span class="pill">статус ${esc(m.status)}</span><span class="pill">сумма ${m.amount}</span>
 <span class="pill">${esc(m.mode)}</span><span class="pill">${m.llm_calls} LLM-вызовов</span><span class="pill">$${m.cost}</span><span class="pill">${m.wall_s} с</span>
 ${m.injection?`<span class="pill inj">инъекция ${esc(m.injection)}${m.injection_applied?'':' (не сработала)'}</span>`:''}${m.stopped_by?`<span class="pill block">остановлен: ${esc(m.stopped_by.point)} ${esc(m.stopped_by.verifier)}</span>`:''}
 ${m.error?`<span class="pill block">${esc(m.error)}</span>`:''}</div>
 <p class="s">run_id ${esc(m.run_id)} · split ${m.split} · git ${esc((m.git_sha||'').slice(0,7))} · метка PR #477: ${esc(m.pr477)}</p>
 <h3>Итог оркестратора</h3><pre>${esc(m.orchestrator_summary)}</pre>
 <div class="grid2"><div><h3>БД до</h3><pre>${J(r.db_initial)}</pre></div><div><h3>БД после</h3><pre>${J(r.db_final)}</pre></div></div>
 <h3>Вердикты по точкам</h3>${matrix(r)}
 ${r.p7?`<h3>P7: аннотатор MAST (V5)</h3><span class="pill ${r.p7.decision}">${r.p7.decision||'error'}</span> ${Object.entries(r.p7.modes||{}).filter(([k,v])=>v).map(([k])=>`<span class="pill">${k}</span>`).join('')}<pre>${esc(r.p7.reason||r.p7.error)}</pre>`:''}
 <h3>Лента шагов (${steps.length})</h3>${steps.map(stepHtml).join('')}`;window.scrollTo(0,0);$('#main').scrollTop=0}
list();
</script></body></html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("trace_files", nargs="+", help="paths relative to experiments/finbot-probe")
    parser.add_argument("--out", help="output name (default: first file's stem)")
    args = parser.parse_args()
    runs = []
    for name in args.trace_files:
        with (EXPERIMENT_DIR / name).open(encoding="utf-8") as f:
            runs += [_prepare(json.loads(line)) for line in f if line.strip()]
    label = args.out or Path(args.trace_files[0]).stem
    data = json.dumps({"label": label, "runs": runs}, ensure_ascii=False, default=str)
    out = EXPERIMENT_DIR / "viewer" / f"{label}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(PAGE.replace("__DATA__", data.replace("</", "<\\/")), encoding="utf-8")
    print(f"{len(runs)} runs -> {out} ({out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
