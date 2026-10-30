#!/bin/zsh
# usage: run_set.sh <scenarios.json> <pristine.db> <port> <outdir> <dbfile> <budget>
SP=${0:A:h}   # вспомогательные скрипты и данные — в этой папке
FB=${0:A:h:h:h}/finbot-pr477
SCN=$1; PRIS=$2; PORT=$3; OUTDIR=$4; DBF=$5; BUDGET=$6; MODEL=$7; total=0
mkdir -p $OUTDIR; cp $SCN $OUTDIR/scenarios.json; cd $FB
export DATABASE_URL=sqlite://$DBF
N=$(python3 -c "import json;print(len(json.load(open('$SCN'))))")
for i in $(seq 0 $((N-1))); do
  if (( $(echo "$total >= $BUDGET" | bc -l) )); then echo "BUDGET STOP at $i total=$total"; break; fi
  id=$(python3 -c "import json;print(json.load(open('$SCN'))[$i]['id'])")
  rm -f $DBF $DBF-wal $DBF-shm; cp $PRIS $DBF
  .venv/bin/python $SP/hook_receiver.py $OUTDIR/$id.hooks.jsonl $PORT & RPID=$!
  sleep 0.7
  $SP/fb.sh env DATABASE_URL=sqlite://$DBF LLM_DEFAULT_MODEL=$MODEL .venv/bin/python $SP/run_record_one.py $SCN $i $OUTDIR/$id.calls.jsonl > $OUTDIR/$id.out.txt 2>&1
  kill $RPID 2>/dev/null; wait $RPID 2>/dev/null
  sqlite3 -json $DBF "select i.invoice_number, i.amount, i.status as invoice_status, v.status as vendor_status, v.trust_level, v.risk_level,
     (select count(*) from payment_transactions p where p.invoice_id=i.id) as payments
     from invoices i join vendors v on v.id=i.vendor_id where i.invoice_number like 'INV-2026-1%';" > $OUTDIR/$id.db.json
  c=$(grep -h '^COST_USD' $OUTDIR/$id.out.txt | awk '{print $2}'); total=$(echo "$total + ${c:-0}" | bc -l)
  echo "$(basename $OUTDIR) $i $id: cost=${c:-?} total=$total | $(tr -d '\n' < $OUTDIR/$id.db.json | grep -o '"invoice_status":"[a-z]*"\|"payments":[0-9]*\|"risk_level":"[a-z]*"' | tr '\n' ' ') | hooks=$(wc -l < $OUTDIR/$id.hooks.jsonl 2>/dev/null)"
done
rm -f $DBF $DBF-wal $DBF-shm
echo "DONE $OUTDIR total=$total"
