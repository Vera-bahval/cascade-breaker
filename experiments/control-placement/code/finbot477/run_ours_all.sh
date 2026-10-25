#!/bin/zsh
SP=${0:A:h}   # вспомогательные скрипты и данные — в этой папке
FB=${0:A:h:h:h}/finbot-pr477
OUTDIR=${0:A:h:h}/runs/finbot477_ours_$(date +%Y%m%d_%H%M%S)
BUDGET=0.80; total=0
mkdir -p $OUTDIR; cp $SP/our_scenarios.json $OUTDIR/scenarios.json; cd $FB
N=$(python3 -c "import json;print(len(json.load(open('$SP/our_scenarios.json'))))")
for i in $(seq 0 $((N-1))); do
  if (( $(echo "$total >= $BUDGET" | bc -l) )); then echo "BUDGET STOP at $i, total=$total"; break; fi
  id=$(python3 -c "import json;print(json.load(open('$SP/our_scenarios.json'))[$i]['id'])")
  rm -f finbot.db-wal finbot.db-shm; cp $SP/finbot_pristine_trusted.db finbot.db
  .venv/bin/python $SP/hook_receiver.py $OUTDIR/$id.hooks.jsonl & RPID=$!
  sleep 0.7
  $SP/fb.sh .venv/bin/python $SP/run_ours_one.py $SP/our_scenarios.json $i > $OUTDIR/$id.out.txt 2>&1
  kill $RPID 2>/dev/null; wait $RPID 2>/dev/null
  sqlite3 -json finbot.db "select i.invoice_number, i.amount, i.status as invoice_status, v.status as vendor_status, v.trust_level, v.risk_level,
     (select count(*) from payment_transactions p where p.invoice_id=i.id) as payments
     from invoices i join vendors v on v.id=i.vendor_id where i.invoice_number like 'INV-2026-1%';" > $OUTDIR/$id.db.json
  c=$(grep -h '^COST_USD' $OUTDIR/$id.out.txt | awk '{print $2}'); total=$(echo "$total + ${c:-0}" | bc -l)
  echo "$i $id: cost=${c:-?} total=$total | $(tr -d '\n' < $OUTDIR/$id.db.json | cut -c1-170) | hooks=$(wc -l < $OUTDIR/$id.hooks.jsonl 2>/dev/null)"
done
rm -f finbot.db-wal finbot.db-shm; cp $SP/finbot_pristine_trusted.db finbot.db
echo "DONE OUTDIR=$OUTDIR total=$total"
