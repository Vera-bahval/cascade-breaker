#!/bin/zsh
# Добивает незавершённые сеты бейзлайна: vera7 до 7×10 и fpr до 150 честных.
# Пропускает уже готовые прогоны (если .db.json есть) — платим только за недостающее.
# Сухой план:  zsh code/finbot477/run_nano_complete.sh dry
# Запуск:      zsh code/finbot477/run_nano_complete.sh
export LC_NUMERIC=C
SP=${0:A:h}; ROOT=${SP:h:h}; FB=$ROOT/finbot-pr477
MODEL=openai/gpt-5-nano; TEMP=0; BUDGET=4.00
DRY=0; [[ "$1" == dry ]] && DRY=1
TRUSTED=$SP/finbot_pristine_trusted.db
total=0

complete () {   # $1=scenarios.json  $2=existing_dir  $3=reps
  local SCN=$1 OUT=$2 REPS=$3
  local IDS=("${(@f)$(python3 -c "import json;[print(s['id']) for s in json.load(open('$SCN'))]")}")
  local N=${#IDS}
  local todo=0
  for rep in $(seq 1 $REPS); do for id in $IDS; do [[ -f $OUT/${id}-r$rep.db.json ]] || todo=$((todo+1)); done; done
  local EST=$(python3 -c "print(f'{$todo*0.0202:.2f}')")
  echo "\n==== ${OUT:t}: всего $((N*REPS)), недостаёт $todo → ≈ \$$EST ===="
  (( DRY )) && return
  cd $FB
  for rep in $(seq 1 $REPS); do
   local i=0
   for id in $IDS; do
    local fid=${id}-r$rep
    if [[ -f $OUT/$fid.db.json ]]; then i=$((i+1)); continue; fi
    (( $(echo "$total >= $BUDGET" | bc -l) )) && { echo "BUDGET STOP total=$total"; return; }
    rm -f finbot.db-wal finbot.db-shm; cp $TRUSTED finbot.db
    .venv/bin/python $SP/hook_receiver.py $OUT/$fid.hooks.jsonl & local RPID=$!
    sleep 0.7
    $SP/fb.sh env LLM_DEFAULT_MODEL=$MODEL LLM_DEFAULT_TEMPERATURE=$TEMP \
      .venv/bin/python $SP/run_ours_one.py $SCN $i > $OUT/$fid.out.txt 2>&1
    kill $RPID 2>/dev/null; wait $RPID 2>/dev/null
    sqlite3 -json finbot.db "select i.invoice_number, i.amount, i.status as invoice_status, v.status as vendor_status,
       v.trust_level, v.risk_level,
       (select count(*) from payment_transactions p where p.invoice_id=i.id) as payments
       from invoices i join vendors v on v.id=i.vendor_id where i.invoice_number like 'INV-2026-1%';" > $OUT/$fid.db.json
    local c=$(grep -h '^COST_USD' $OUT/$fid.out.txt | awk '{print $2}'); total=$(echo "$total + ${c:-0}" | bc -l)
    echo "$fid: total=$total | $(tr -d '\n' < $OUT/$fid.db.json | cut -c1-90)"
    i=$((i+1))
   done
  done
  echo "DONE ${OUT:t}"
}

V7=$(ls -td $ROOT/code/runs/finbot477_nanobase_vera7_* 2>/dev/null | head -1)
FUN=$(ls -td $ROOT/code/runs/finbot477_nanobase_funnel_* 2>/dev/null | head -1)
FPR=$(ls -td $ROOT/code/runs/finbot477_nanobase_fpr_* 2>/dev/null | head -1)
[[ -z $V7 || -z $FUN || -z $FPR ]] && { echo "нет папок бейзлайна — сперва run_nano_baseline.sh"; exit 1; }
complete $SP/vera7_scenarios.json     $V7  10   # сверка с Даней
complete $SP/our_scenarios.json       $FUN 1    # воронка: один полный проход 77
complete $SP/v6_honest_scenarios.json $FPR 1    # FPR: 150 честных
echo "\nИтого добито, потрачено ~\$$total. Папки: ${V7:t}, ${FUN:t}, ${FPR:t}"
