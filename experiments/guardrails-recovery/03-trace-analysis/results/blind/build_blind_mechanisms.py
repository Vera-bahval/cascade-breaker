"""Слепой пакет для независимой разметки механизмов (22.11.2026). Только чтение трасс; LLM не вызываются.

  finbot-pr477/.venv/bin/python analysis_2026-11-22/blind/build_blind_mechanisms.py

Листы (blind/sheets/, UTF-8 с BOM):
  A1_transfer.csv   — сигнал Fraud + поручение оркестратора для Payments (без действий и исхода Payments);
  A2_payments.csv   — вход и действия Payments на тех же прогонах (другие ID, порядок другой);
  B1_fraud_text.csv — итог Fraud: есть ли условие и какое (88 кандидатов + 30 случайных «отвлекающих» без условия по детектору);
  B2_delivery.csv   — условие (цитата из B1-ключа) + вход Payments: дошло ли условие до Payments (без исхода);
  C_orch_stops.csv  — одобренные счета, где оркестратор не позвал Payments: обоснован ли останов (выборка со стратами).
Ключ — blind/KEY_CLOSED/ (не открывать разметчикам). Маскируются: версия FinBot, модель, серия, ID сценария/профиля,
пространства имён и нестандартные номера счетов, слова-шаблоны задания («independent(ly)»), заголовок Prior context."""
import ast, csv, glob, json, os, random, re, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
AN = os.path.dirname(HERE)
ROOT = os.path.dirname(AN)
sys.path.insert(0, AN); sys.path.insert(0, os.path.join(ROOT, "code")); sys.path.insert(0, os.path.join(ROOT, "CascadeLab/iv_lab"))
import traces_analysis as T
import flash_vs_nano as FV
from fx_analysis import stop_demand

SEED = "BLIND-MECH-20261122"
MAXLEN = 6000
os.makedirs(os.path.join(HERE, "sheets"), exist_ok=True)
os.makedirs(os.path.join(HERE, "KEY_CLOSED"), exist_ok=True)


def mask(s):
    s = str(s or "")
    s = re.sub(r"\buni-[\w-]+", "[ns]", s)
    s = re.sub(r"\bINV-(?!2026-000\d\b)[\w-]+", "INV-[cur]", s)
    s = re.sub(r"\bindependent(ly)?\b", "[…]", s, flags=re.I)
    s = re.sub(r"Prior workflow context[^\n:]*:?", "[context from previous steps]:", s, flags=re.I)
    s = re.sub(r"\b(gpt-5-nano|gpt-4o-mini|deepseek[\w./-]*|a7f6964|PR ?#?8)\b", "[m]", s, flags=re.I)
    s = re.sub(r"\b(wf|sess)_[\w-]+", "[id]", s)
    return s[:MAXLEN]


MONEY = re.compile(r"\$\s?\d[\d,]*(\.\d+)?|\b\d[\d,]*\.\d+\b|\b\d{1,3}(,\d{3})+\b")
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}(T[\d:.]+Z?)?\b")
IDTOK = re.compile(r"\btr_[0-9a-f]{8,}\b|\b(?:[A-Z]{1,6}[#-]?)?\d{3,}(?:[-/][A-Z0-9]+)*\b|\b[A-Z]{1,6}-\d+[\w-]*\b")


def pseudo_row(row, fields, keep_amount_tokens=True):
    """Псевдонимы идентификаторов внутри одной строки (единые для всех её полей): номера счетов, поставщиков,
    PO, договоров, переводов → [#1], [#2]…; суммы, даты, проценты не трогаются. Отображение своё у каждой строки,
    поэтому одинаковые трассы в разных листах не связываются по номерам."""
    mp = {}

    def sub(text):
        protected = {}
        def keep(m):
            k = f"\x00{len(protected)}\x00"; protected[k] = m.group(0); return k
        t = DATE.sub(keep, text)
        t = MONEY.sub(keep, t) if keep_amount_tokens else t
        t = re.sub(r"\b\d{1,3}(\.\d+)?\s?%", keep, t)
        t = IDTOK.sub(lambda m: mp.setdefault(m.group(0), f"[#{len(mp) + 1}]"), t)
        for k, v in protected.items():
            t = t.replace(k, v)
        return t
    for f in fields:
        row[f] = sub(row[f])
    return row


def arg(a):
    if isinstance(a, str):
        try: a = ast.literal_eval(a)
        except Exception:
            try: a = json.loads(a)
            except Exception: a = {}
    return a or {}


# ---------------------------------------------------------------- извлечение по агентам
def from_unified(path):
    r = json.load(open(os.path.join(ROOT, path)))
    st = [s for t in r["traces"].values() for s in t["steps"]]
    ag = lambda name: [s for s in st if s.get("agent") == name]
    pay = ag("payments_agent")
    pin = next((s.get("messages") for s in pay if s["kind"] == "llm"), None)
    pin_user = ""
    if pin:
        msgs = pin if isinstance(pin, list) else arg(pin)
        if isinstance(msgs, list):
            pin_user = "\n".join(str(m.get("content")) for m in msgs if isinstance(m, dict) and m.get("role") == "user")
    if not pin_user:
        pin_user = " || ".join(s.get("enriched_task") or s.get("task_description") or "" for s in st if s["kind"] == "delegation" and s.get("target") == "payments")
    pay_steps = []
    for s in pay:
        if s["kind"] == "tool":
            pay_steps.append(f"TOOL {s.get('name')} ARGS {s.get('arguments')}\n  → {str(s.get('output'))[:700]}")
        elif s["kind"] == "llm":
            o = arg(s.get("output")) if isinstance(s.get("output"), str) else (s.get("output") or {})
            c = o.get("content") if isinstance(o, dict) else str(s.get("output"))
            if c and str(c).strip():
                pay_steps.append(f"THINK {str(c)[:900]}")
    flags = [arg(s.get("arguments")) for s in st if s["kind"] == "tool" and s.get("name") == "flag_invoice_for_review"]
    return dict(
        fraud_flag="\n".join(f"reason={f.get('flag_reason')} action={f.get('recommended_action')} notes={f.get('agent_notes')}" for f in flags) or "нет флага",
        fraud_summary=" ".join(s.get("task_summary", "") for s in st if s["kind"] == "summary" and s.get("agent") == "fraud_agent"),
        orch_pay_task=" || ".join(s.get("task_description") or "" for s in st if s["kind"] == "delegation" and s.get("target") == "payments") or "Payments не вызван",
        orch_reasoning=" ".join(str(arg(s.get("output")).get("content") if isinstance(s.get("output"), str) else s.get("output"))[:600]
                                for s in st if s["kind"] == "llm" and s.get("agent") == "orchestrator_agent"),
        invoice_note=" ".join(str(arg(s.get("arguments")).get("agent_notes", "")) for s in st if s["kind"] == "tool" and s.get("name") == "update_invoice_status"),
        payments_input=pin_user, payments_steps="\n".join(pay_steps))


def blocks_from_hooks(rows):
    """Хуки → по агентам: первый вход модели, инструменты с результатами, выводы модели."""
    stack, B = ["orchestrator"], {}
    get = lambda n: B.setdefault(n, dict(received=None, steps=[], outputs=[]))
    for r in rows:
        k, tool = r.get("hook_kind"), r.get("tool_name") or ""
        cur = get(stack[-1])
        if k == "before_model" and cur["received"] is None:
            cur["received"] = r.get("user_message")
        elif k == "after_model" and r.get("model_output"):
            cur["outputs"].append(str(r.get("model_output"))[:900])
        elif k == "before_tool" and tool.startswith("delegate_to_"):
            cur["steps"].append(f"DELEGATE {tool} ARGS {r.get('tool_arguments')}")
            stack.append(tool[len("delegate_to_"):])
        elif k == "after_tool" and tool.startswith("delegate_to_"):
            if len(stack) > 1: stack.pop()
            get(stack[-1])["steps"].append(f"RESULT {tool} → {str(r.get('tool_result'))[:1500]}")
        elif k == "after_tool":
            cur["steps"].append(f"TOOL {tool} ARGS {r.get('tool_arguments')}\n  → {str(r.get('tool_result'))[:700]}")
    return B


PRE = {}
def pre_index():
    if PRE: return PRE
    for lab, ld in (("pre-nano-227", FV.load_nano), ("pre-flash-227", FV.load_flash)):
        for k, ep in ld().items():
            PRE[(lab, k)] = ep
    return PRE


def from_pre(group, scenario):
    ep = pre_index()[(group, scenario)]
    rows = ep["rows"]; B = blocks_from_hooks(rows)
    bt = [r for r in rows if r.get("hook_kind") == "before_tool"]
    flags = [arg(r.get("tool_arguments")) for r in bt if r.get("tool_name") == "flag_invoice_for_review"]
    pay = B.get("payments", {})
    return dict(
        fraud_flag="\n".join(f"reason={f.get('flag_reason')} action={f.get('recommended_action')} notes={f.get('agent_notes')}" for f in flags) or "нет флага",
        fraud_summary=" ".join(str(r.get("tool_result")) for r in rows if r.get("hook_kind") == "after_tool" and r.get("tool_name") == "delegate_to_fraud"),
        orch_pay_task=" || ".join(str(arg(r.get("tool_arguments")).get("task_description", "")) for r in bt if r.get("tool_name") == "delegate_to_payments") or "Payments не вызван",
        # у nano вывод модели в хуках пуст — показываем действия оркестратора (поручения и их результаты)
        orch_reasoning=(" ".join(B.get("orchestrator", {}).get("outputs", [])) or
                        "[рассуждение не записано; действия:]\n" + "\n".join(B.get("orchestrator", {}).get("steps", [])))[:4000],
        invoice_note=" ".join(str(arg(r.get("tool_arguments")).get("agent_notes", "")) for r in bt if r.get("tool_name") == "update_invoice_status"),
        payments_input=pay.get("received") or "",
        payments_steps="\n".join(pay.get("steps", []) + [f"THINK {o}" for o in pay.get("outputs", [])]))


def extract(row):
    return from_unified(row["path"]) if row["group"].startswith("post") else from_pre(row["group"], row["scenario"])


def write(name, rows):
    if not rows: return
    w = csv.DictWriter(open(os.path.join(HERE, name), "w", newline="", encoding="utf-8-sig"), fieldnames=list(rows[0]))
    w.writeheader(); w.writerows(rows)


def main():
    rnd = random.Random(SEED)
    key = []
    # ---------- A: флаг + Payments вызван (все одобренные с флагом из post-noguard и pre-227)
    F = [r for r in csv.DictReader(open(os.path.join(AN, "flag_to_payments.csv"), encoding="utf-8-sig"))
         if r["task_class"] != "orch_did_not_call_payments" and r["group"] in ("post-noguard", "pre-flash-227", "pre-nano-227")]
    rnd.shuffle(F)
    A1, A2 = [], []
    for i, r in enumerate(F, 1):
        x = extract(r)
        A1.append(pseudo_row(dict(id=f"A1-{i:03d}", fraud_flag=mask(x["fraud_flag"]), fraud_summary=mask(x["fraud_summary"]),
                       orchestrator_task_for_payments=mask(x["orch_pay_task"]),
                       a1_signal_strength="", a1_task_relation="", a1_scope_match="", a1_comment=""),
                       ["fraud_flag", "fraud_summary", "orchestrator_task_for_payments"]))
        key.append(dict(blind_id=f"A1-{i:03d}", sheet="A1", group=r["group"], scenario=r["scenario"], honest=r["honest"],
                        paid=r["paid"], auto_task_class=r["task_class"], claude_label="", path=r["path"]))
    order = list(range(len(F))); rnd.shuffle(order)
    for j, i in enumerate(order, 1):
        r = F[i]; x = extract(r)
        A2.append(pseudo_row(dict(id=f"A2-{j:03d}", payments_input=mask(x["payments_input"]), payments_steps=mask(x["payments_steps"]),
                       a2_saw_hold="", a2_hold_treatment="", a2_own_check="", a2_check_matches_flag_reason="", a2_comment=""),
                       ["payments_input", "payments_steps"]))
        key.append(dict(blind_id=f"A2-{j:03d}", sheet="A2", group=r["group"], scenario=r["scenario"], honest=r["honest"],
                        paid=r["paid"], auto_task_class=r["task_class"], claude_label="", path=r["path"]))
    write("sheets/A1_transfer.csv", A1); write("sheets/A2_payments.csv", A2)

    # ---------- B: 88 кандидатов + 30 отвлекающих (одобрен, флага нет, детектор «none»)
    C = list(csv.DictReader(open(os.path.join(AN, "text_hold_no_flag_candidates.csv"), encoding="utf-8-sig")))
    allruns = list(T.unified_runs()) + list(T.pre227("pre-nano-227", FV.load_nano)) + list(T.pre227("pre-flash-227", FV.load_flash))
    cand_keys = {(c["group"], c["scenario"], c["path"]) for c in C}
    neg = []
    for r in allruns:
        if r["kind"] == "invoice" and r["approved"] and r["fraud_called"] and not r["flag"] and stop_demand(r["fsum"])[0] == "none":
            grp = r["src"] if r["src"] != "unified" else ("post-noguard" if not r["guard"] else "post-guard")
            if (grp, r["scenario"], r["path"]) not in cand_keys:
                neg.append(dict(group=grp, scenario=r["scenario"], path=r["path"], honest=str(r["honest"]), paid=str(r["paid"]),
                                level_auto="none(distractor)", pay_called=str(bool(r["pay_tasks"]))))
    rnd.shuffle(neg)
    Bset = [dict(c, role="candidate") for c in C] + [dict(n, role="distractor") for n in neg[:30]]
    rnd.shuffle(Bset)
    B1, B2 = [], []
    for i, r in enumerate(Bset, 1):
        x = extract(r)
        B1.append(pseudo_row(dict(id=f"B1-{i:03d}", fraud_summary=mask(x["fraud_summary"]),
                       b1_condition_class="", b1_condition_quote="", b1_condition_target="", b1_comment=""), ["fraud_summary"]))
        key.append(dict(blind_id=f"B1-{i:03d}", sheet="B1", group=r["group"], scenario=r["scenario"], honest=r["honest"],
                        paid=r["paid"], auto_task_class=r.get("level_auto"), claude_label="", path=r["path"], role=r["role"]))
    cand = [r for r in Bset if r["role"] == "candidate" and r.get("pay_called") == "True"]
    rnd.shuffle(cand)
    for j, r in enumerate(cand, 1):
        x = extract(r)
        B2.append(pseudo_row(dict(id=f"B2-{j:03d}", condition_from_fraud=mask(r["snippet"]), payments_input=mask(x["payments_input"]),
                       b2_delivered="", b2_delivery_form="", b2_comment=""), ["condition_from_fraud", "payments_input"]))
        key.append(dict(blind_id=f"B2-{j:03d}", sheet="B2", group=r["group"], scenario=r["scenario"], honest=r["honest"],
                        paid=r["paid"], auto_task_class=r.get("payments_task_class"), claude_label="", path=r["path"], role="candidate"))
    write("sheets/B1_fraud_text.csv", B1); write("sheets/B2_delivery.csv", B2)

    # ---------- C: остановы оркестратора на одобренных (честных по метке) — выборка по стратам
    S = list(csv.DictReader(open(os.path.join(AN, "orch_false_stops.csv"), encoding="utf-8-sig")))
    strata = {}
    for r in S:
        strata.setdefault((r["group"].split("-")[0] + ("-nano" if "nano" in r["group"] else "-flash"), r["fraud_flag"]), []).append(r)
    pick = []
    for k in sorted(strata):
        L = strata[k][:]; rnd.shuffle(L); pick += L[:20]
    rnd.shuffle(pick)
    Cs = []
    for i, r in enumerate(pick, 1):
        x = extract(r)
        Cs.append(pseudo_row(dict(id=f"C-{i:03d}", invoice_agent_note=mask(x["invoice_note"]), fraud_flag=mask(x["fraud_flag"]),
                       fraud_summary=mask(x["fraud_summary"]), orchestrator_reasoning=mask(x["orch_reasoning"]),
                       c_stop_reasonable="", c_stop_basis="", c_comment=""),
                       ["invoice_agent_note", "fraud_flag", "fraud_summary", "orchestrator_reasoning"]))
        key.append(dict(blind_id=f"C-{i:03d}", sheet="C", group=r["group"], scenario=r["scenario"], honest="True",
                        paid="False", auto_task_class=f"fraud_flag={r['fraud_flag']}", claude_label="", path=r["path"],
                        role="stratum " + ";".join(f"{k[0]}/flag={k[1]}" for k in strata if r in strata[k])))
    write("sheets/C_orch_stops.csv", Cs)
    cols = sorted({k for x in key for k in x}, key=lambda c: ["blind_id", "sheet"].index(c) if c in ("blind_id", "sheet") else 9)
    w = csv.DictWriter(open(os.path.join(HERE, "KEY_CLOSED/key.csv"), "w", newline="", encoding="utf-8-sig"), fieldnames=cols)
    w.writeheader(); w.writerows(key)
    print("A1", len(A1), "A2", len(A2), "B1", len(B1), "(кандидатов", len(C), "+ отвлекающих", min(30, len(neg)), ") B2", len(B2), "C", len(Cs),
          "| страты C:", {f"{k[0]}/flag={k[1]}": len(v) for k, v in strata.items()})


if __name__ == "__main__":
    main()
