#!/bin/zsh
# Runs Vera's 7 cascade scenarios x REPEATS on a fresh DB each time, recording hooks + outcome. No FinBot code changes.
SP=${0:A:h}   # вспомогательные скрипты и данные — в этой папке
FB=${0:A:h:h:h}/finbot-pr477
OUTDIR=${0:A:h:h}/runs/finbot477_$(date +%Y%m%d_%H%M%S)
REPEATS=${1:-2}
mkdir -p $OUTDIR; cd $FB
for rep in $(seq 1 $REPEATS); do for idx in 1 2 3 4 5 6 7; do
  tag=s${idx}_r${rep}
  rm -f finbot.db-wal finbot.db-shm; cp $SP/finbot_pristine.db finbot.db
  .venv/bin/python $SP/hook_receiver.py $OUTDIR/$tag.hooks.jsonl & RPID=$!
  sleep 0.7
  $SP/fb.sh .venv/bin/python $SP/run_one_scenario.py $idx 0.05 > $OUTDIR/$tag.out.txt 2>&1
  kill $RPID 2>/dev/null; wait $RPID 2>/dev/null
  sqlite3 -json finbot.db "select i.id, i.amount, i.status as invoice_status, v.status as vendor_status, v.trust_level, v.risk_level,
     (select count(*) from payment_transactions p where p.invoice_id=i.id) as payments,
     (select coalesce(sum(amount),0) from payment_transactions p where p.invoice_id=i.id) as paid_amount,
     (select count(*) from emails) as emails
     from invoices i join vendors v on v.id=i.vendor_id;" > $OUTDIR/$tag.db.json
  echo "$tag: $(grep -h '== LLM' $OUTDIR/$tag.out.txt) | $(tr -d '\n' < $OUTDIR/$tag.db.json | cut -c1-220)"
done; done
rm -f finbot.db-wal finbot.db-shm; cp $SP/finbot_pristine.db finbot.db
echo OUTDIR=$OUTDIR
