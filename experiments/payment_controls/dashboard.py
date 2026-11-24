"""Regenerate the standalone archive-audit dashboard."""
import csv
import html
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    rows = list(csv.DictReader((HERE / "archive_audit.csv").open()))
    blind = {x["scenario"]: x for x in json.loads((HERE / "blind_p0.json").read_text())}
    counts = Counter(x["author_label"] for x in rows)
    table = []
    for row in rows:
        label = blind[row["scenario"]]
        cells = [row["run"], row["author_label"], row["amount"], row["control"],
                 f"{label['a']} / {label['b']}", row["flag_calls"], row["checks_before_transfer"]]
        table.append("<tr>" + "".join(f"<td>{html.escape(x)}</td>" for x in cells) + "</tr>")
    doc = """<!doctype html><html lang="ru"><meta charset="utf-8"><title>FinBot · Аудит архива</title>
<style>body{font:16px system-ui;color:#18283b;margin:3vw}table{border-collapse:collapse;width:100%}
th,td{text-align:left;border-bottom:1px solid #ccd4df;padding:.55rem}td:last-child{font:13px monospace}
input{padding:.5rem;width:22rem}p{max-width:80ch}</style>
<h1>Пропущенные переводы ЧП2</h1><p>Архивная диагностика. Каждый ряд связывает решение защитника
с записью перевода. Авторская категория задаёт ожидаемый исход сценария. Бизнес-обоснованность оплаты
оценивается отдельно. Решение Terra относится к допуску на обработку в P0.</p>"""
    doc += f"<p>{len(rows)} прогонов · {len(blind)} уникальных входов слепой проверки с контролями · {html.escape(str(dict(counts)))}</p>"
    doc += """<label>Фильтр <input id="filter" type="search" placeholder="Сценарий, категория или точка"></label>
<table><thead><tr><th>Прогон<th>Категория автора<th>Сумма<th>Честный контроль<th>Terra на P0<th>Вызовов HOLD¹<th>Точки до перевода</tr></thead>
<tbody>""" + "".join(table) + """</tbody></table><p>¹ Считаются вызовы flag_invoice_for_review до первого перевода.</p>
<script>document.querySelector('#filter').oninput=e=>document.querySelectorAll('tbody tr').forEach(r=>{
r.hidden=!r.textContent.toLowerCase().includes(e.target.value.toLowerCase())})</script></html>"""
    (HERE / "archive.html").write_text(doc)


def pilot_dashboard():
    """Public, offline view. Metrics are for document decisions only."""
    path = HERE / "pilot_results.csv"
    if not path.exists():
        return
    with path.open() as f:
        observations = list(csv.DictReader(f))
    title = "FinBot · Диагностический пилот"
    page = f"""<!doctype html><html lang="ru"><meta charset="utf-8"><title>{title}</title>
<style>body{{font:16px system-ui;color:#172e43;margin:3vw}} label{{display:inline-block;margin:.4em}}
table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;padding:.5rem;border-bottom:1px solid #ccd4df}}
p{{max-width:90ch}} .error{{background:#fff3ea}} select{{padding:.3rem}}</style>
<h1>{title}</h1><p>Решение о делегировании после Fraud по первичному документу. Итог по выбранным строкам учитывает повторные измерения одного документа.
Полная стоимость платёжного workflow измеряется отдельно.</p><div id="filters"></div><p id="totals"></p><table><thead><tr>"""
    columns = {"phase":"Серия","provider":"Провайдер","case_id":"Документ","mast":"MAST","form":"Вопрос",
               "summary":"С резюме","gold":"Эталон","decision":"Ответ","seconds":"Секунды","cost_usd":"Доллары"}
    page += "".join(f"<th>{label}</th>" for label in columns.values()) + "</tr></thead><tbody>"
    for row in observations:
        attrs = " ".join(f'data-{k}="{html.escape(row[k],quote=True)}"' for k in
                         ("phase","provider","form","summary","mast","correct","cost_usd"))
        cells = []
        for k in columns:
            val = row[k]
            if k == "seconds": val = f"{float(val):.3f}"
            if k == "cost_usd": val = f"{float(val):.9f}"
            cells.append("<td>" + html.escape(val) + "</td>")
        css = "error" if row["correct"] == "0" else ""
        page += f'<tr class="{css}" {attrs}>' + "".join(cells) + "</tr>"
    page += """</tbody></table><script>
const rows=[...document.querySelectorAll('tbody tr')], filters={};
function update(){let n=0, right=0, cost=0;for(const r of rows){
r.hidden=Object.entries(filters).some(([key,sel])=>sel.value&&r.dataset[key]!==sel.value);
if(!r.hidden){n++;right+=Number(r.dataset.correct);cost+=Number(r.dataset.cost_usd)}}
document.querySelector('#totals').textContent='Верно '+right+' из '+n+' ответов · $'+cost.toFixed(9)+
' (Jev по тарифу, Eliza по списанию)';}
for(const [key,label] of Object.entries({phase:'Серия',provider:'Провайдер',form:'Вопрос',summary:'С резюме',mast:'MAST',correct:'Верно'})){
const l=document.createElement('label'),s=document.createElement('select');l.textContent=label+' ';l.append(s);
s.add(new Option('Все',''));for(const v of [...new Set(rows.map(r=>r.dataset[key]))].sort())s.add(new Option(v,v));
s.onchange=update;filters[key]=s;document.querySelector('#filters').append(l);}update();</script></html>"""
    live_path = HERE / "live_pilot_results.csv"
    if live_path.exists():
        with live_path.open() as f:
            live = list(csv.DictReader(f))
        live_fields = (("case","Счёт"), ("guard_point","Точка"), ("guard_decision","Решение Jev"),
                       ("transfer_calls","Вызовы FinStripe"), ("transfers","Переводы в БД"),
                       ("executor_calls","Вызовы DeepSeek"), ("milliseconds","Время, мс"))
        header = "".join(f"<th>{label}</th>" for _, label in live_fields)
        rendered = ["<section><h2>Живые workflow FinBot</h2><table><thead><tr>" + header + "</tr></thead><tbody>"]
        for r in live:
            rendered.append("<tr>" + "".join(f"<td>{html.escape(r[k] or '—')}</td>" for k,_ in live_fields) + "</tr>")
        rendered.append("</tbody></table></section>")
        page = page.replace("</script></html>", "</script>" + "".join(rendered) + "</html>")
    (HERE / "pilot.html").write_text(page)


if __name__ == "__main__":
    main()
    pilot_dashboard()
