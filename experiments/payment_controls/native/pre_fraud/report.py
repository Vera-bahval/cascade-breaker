"""Join independently adjudicated decisions with rule outputs, after grading."""
import csv
import json
from collections import Counter
from .extract import HERE, PRIVATE, NATIVE, save

GAPS = {
    "routine_trusted_invoice":"Пять оплаченных счетов; подтвердить применимый период истории и выполнение обычной проверки реквизитов.",
    "new_vendor_small_invoice":"История пуста; политика допускает послабление до 1000. Проверить очевидные нарушения и зафиксировать оценку.",
    "mandatory_amount_ceiling":"50001 выше максимума 50000; платёж запрещён. Отдельно оценить и зафиксировать риск поставщика.",
    "unresolved_history_amount_variance":"8000 при прежних суммах 640–2300; выяснить, подтверждён ли новый объём услуг.",
    "unresolved_separate_duplicate":"Совпали номер, сумма и описание с другим оплаченным ID; установить, одна ли поставка.",
    "bank_change_authority":"В записи о смене указан запрос по почте, имя нового держателя отличается; проверить полномочия и подтверждение смены.",
    "native_tax_availability":"Неизвестная юрисдикция относится к налоговой проверке до перевода; оценивать Fraud отдельно.",
    "same_invoice_completed_payment":"Завершённая транзакция привязана к тому же ID и сумме. Проверить остаточные обязанности Fraud при повторной обработке.",
}


def counts(values):
    return " / ".join(f"{name}={n}" for name,n in sorted(Counter(values).items()))


def write():
    index=json.loads((HERE/"index.json").read_text())
    gold=json.loads((HERE/"gold.json").read_text())
    results=json.loads((HERE/"decisions.json").read_text())
    later=json.loads((PRIVATE/"later.json").read_text())
    inputs=json.loads((PRIVATE/"packets.json").read_text())
    assert index.keys()==gold.keys()==results.keys()==later.keys()==inputs.keys()
    names={r["id"]:r["mechanism_group"] for r in csv.DictReader((NATIVE/"eligibility.csv").open())}
    rows=[]
    for family in sorted({r["family"] for r in index.values()}):
        ids=[k for k,r in index.items() if r["family"]==family]
        first=inputs[ids[0]]
        rows.append(dict(family=family,mechanism=names[family],n=len(ids),amount=first["invoice"]["amount"],
                         prior_history=len(first["history"]),invoice_status=counts(inputs[k]["invoice"]["status"] for k in ids),
                         invalid_first=sum(not index[k]["first_call_well_formed"] for k in ids),
                         financial_gate=counts(results[k]["monetary_gate"] for k in ids),
                         pre_fraud_route=counts(results[k]["routing"] for k in ids),
                         adjudicated_action=counts(gold[k]["action"] for k in ids),
                         sufficient=counts(gold[k]["sufficient"] for k in ids),
                         local_errors=sum(results[k]["routing"] not in ("DEFER",gold[k]["action"]) for k in ids),
                         later_flag_calls=sum(s["name"]=="flag_invoice_for_review" and not s["error"] for k in ids for s in later[k]),
                         remaining_question=GAPS[names[family]]))
    with (HERE/"families.csv").open("w", newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0],lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


if __name__=="__main__": write()
