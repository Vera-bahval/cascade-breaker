#!/bin/zsh
# Бейзлайн на nano: FinBot САМ ПО СЕБЕ (без наших проверок), официальная модель gpt-5-nano.
# Две части: воронка/вред (77-набор our_scenarios) + FPR (150 честных v6_honest).
# Это то, против чего потом меряется охранник. Trusted-база (профиль C) собирается, если её нет.
#
# Сухой план (бесплатно):   zsh code/finbot477/run_nano_baseline.sh dry
# Запуск (~$0.6, ~1 ч):     zsh code/finbot477/run_nano_baseline.sh
export LC_NUMERIC=C
SP=${0:A:h}; ROOT=${SP:h:h}; FB=$ROOT/finbot-pr477
MODEL=openai/gpt-5-nano; TEMP=0; BUDGET=1.00
DRY=0; [[ "$1" == dry ]] && DRY=1
TRUSTED=$SP/finbot_pristine_trusted.db

# --- trusted-база (профиль C, хук на порт 8765) ---
if [[ ! -f $TRUSTED ]]; then
  if (( DRY )); then
    echo "[dry] trusted-базы нет → собрал бы: zsh build_pristine.sh C 8765 → finbot_pristine_trusted.db"
  else
    echo "Собираю trusted-базу (профиль C, порт 8765)…"
    zsh $SP/build_pristine.sh C 8765 >/dev/null && cp $SP/pristine/pristine_C_8765.db $TRUSTED \
      && echo "  готово: finbot_pristine_trusted.db" || { echo "сборка базы не удалась"; exit 1; }
  fi
fi

run_set () {   # $1=scenarios.json  $2=label  $3=repeats
  local SCN=$1 LABEL=$2 REPS=$3
  local N=$(python3 -c "import json;print(len(json.load(open('$SCN'))))")
  local EST=$(python3 -c "print(f'{$N*$REPS*0.0026:.2f}')")
  echo "\n==== $LABEL: $N сценариев × $REPS повтора = $((N*REPS)) прогонов · $MODEL · T=$TEMP → ≈ \$$EST (бюджет \$$BUDGET) ===="
  (( DRY )) && return
  local OUT=$ROOT/code/runs/finbot477_nanobase_${LABEL}_$(date +%Y%m%d_%H%M%S)
  mkdir -p $OUT; cp $SCN $OUT/scenarios.json; cd $FB
  echo "  → $OUT"
  local total=0
  for rep in $(seq 1 $REPS); do
   for i in $(seq 0 $((N-1))); do
    (( $(echo "$total >= $BUDGET" | bc -l) )) && { echo "BUDGET STOP at rep$rep/$i, total=$total"; break 2; }
    local id=$(python3 -c "import json;print(json.load(open('$SCN'))[$i]['id'])")-r$rep
    rm -f finbot.db-wal finbot.db-shm; cp $TRUSTED finbot.db
    .venv/bin/python $SP/hook_receiver.py $OUT/$id.hooks.jsonl & local RPID=$!
    sleep 0.7
    $SP/fb.sh env LLM_DEFAULT_MODEL=$MODEL LLM_DEFAULT_TEMPERATURE=$TEMP \
      .venv/bin/python $SP/run_ours_one.py $SCN $i > $OUT/$id.out.txt 2>&1
    kill $RPID 2>/dev/null; wait $RPID 2>/dev/null
    sqlite3 -json finbot.db "select i.invoice_number, i.amount, i.status as invoice_status, v.status as vendor_status,
       v.trust_level, v.risk_level,
       (select count(*) from payment_transactions p where p.invoice_id=i.id) as payments
       from invoices i join vendors v on v.id=i.vendor_id where i.invoice_number like 'INV-2026-1%';" > $OUT/$id.db.json
    local c=$(grep -h '^COST_USD' $OUT/$id.out.txt | awk '{print $2}'); total=$(echo "$total + ${c:-0}" | bc -l)
    echo "$id: total=$total | $(tr -d '\n' < $OUT/$id.db.json | cut -c1-110)"
   done
  done
  rm -f finbot.db-wal finbot.db-shm
  echo "DONE $LABEL → ${OUT#$ROOT/} total=$total"
}

run_set $SP/vera7_scenarios.json    vera7  10   # 7 ручных сценариев Веры (Cascade Lab) ×10 — сверка с Даниилом
run_set $SP/our_scenarios.json      funnel 3    # воронка ×3: 34 честных + 43 плохих (атаки/фрод/порог)
run_set $SP/v6_honest_scenarios.json fpr    1    # FPR ×1: 150 РАЗНЫХ честных (повторы те же не нужны)

echo "\nГотово. Папки: code/runs/finbot477_nanobase_funnel_*, code/runs/finbot477_nanobase_fpr_*"
echo "Дальше: воронка (вред) и FPR FinBot на nano — бейзлайн, против которого меряем охранник."
