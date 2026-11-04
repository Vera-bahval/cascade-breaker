#!/bin/zsh
# Пакетный прогон с ПОЛНОЙ записью вызовов и заданной температурой (локальные пути, без временной папки).
# usage: run_set_rec2.sh <scenarios.json> <pristine.db> <port> <outdir> <dbfile> <budget_usd> <model> <temperature>
HERE=${0:A:h}
FB=${HERE:h:h}/finbot-pr477
SCN=${1:A}; PRIS=${2:A}; PORT=$3; OUTDIR=${4:A}; DBF=$5; BUDGET=$6; MODEL=$7; TEMP=$8; total=0
mkdir -p $OUTDIR; cp $SCN $OUTDIR/scenarios.json; cd $FB
N=$(python3 -c "import json;print(len(json.load(open('$SCN'))))")
for i in $(seq 0 $((N-1))); do
  if (( $(echo "$total >= $BUDGET" | bc -l) )); then echo "BUDGET STOP at $i total=$total"; break; fi
  id=$(python3 -c "import json;print(json.load(open('$SCN'))[$i]['id'])")
  rm -f $DBF $DBF-wal $DBF-shm; cp $PRIS $DBF
  .venv/bin/python $HERE/hook_receiver.py $OUTDIR/$id.hooks.jsonl $PORT & RPID=$!
  sleep 0.7
  $HERE/fb.sh env DATABASE_URL=sqlite://$DBF LLM_DEFAULT_MODEL=$MODEL LLM_DEFAULT_TEMPERATURE=$TEMP \
     .venv/bin/python $HERE/run_record_one.py $SCN $i $OUTDIR/$id.calls.jsonl > $OUTDIR/$id.out.txt 2>&1
  kill $RPID 2>/dev/null; wait $RPID 2>/dev/null
  sqlite3 -json $DBF "select i.invoice_number, i.amount, i.status as invoice_status, v.status as vendor_status, v.trust_level, v.risk_level,
     (select count(*) from payment_transactions p where p.invoice_id=i.id) as payments
     from invoices i join vendors v on v.id=i.vendor_id where i.invoice_number like 'INV-2026-1%';" > $OUTDIR/$id.db.json
  c=$(grep -h '^COST_USD' $OUTDIR/$id.out.txt | awk '{print $2}'); total=$(echo "$total + ${c:-0}" | bc -l)
  echo "$(basename $OUTDIR) $i $id: cost=${c:-?} total=$total | $(tr -d '\n' < $OUTDIR/$id.db.json | grep -o '"invoice_status":"[a-z]*"\|"payments":[0-9]*' | tr '\n' ' ') | hooks=$(wc -l < $OUTDIR/$id.hooks.jsonl 2>/dev/null)"
done
rm -f $DBF $DBF-wal $DBF-shm
echo "DONE $OUTDIR total=$total"
