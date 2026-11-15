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


if __name__ == "__main__":
    main()
