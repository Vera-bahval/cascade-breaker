#!/bin/zsh
# Прогон «пар»: каждый сценарий — отдельным файлом из одного счёта, чтобы номер счёта был одинаков у всех (INV-2026-1000).
# Внутри вызывает run_set_rec2.sh (полная запись, температура параметром). Бюджет — общий на весь набор.
# usage: run_pairs.sh <scenarios.json> <pristine.db> <port> <outdir> <dbfile> <budget_usd> <model> <temperature>
HERE=${0:A:h}; setopt nullglob
SCN=${1:A}; PRIS=${2:A}; PORT=$3; OUTDIR=${4:A}; DBF=$5; BUDGET=$6; MODEL=$7; TEMP=$8
mkdir -p $OUTDIR
N=$(python3 -c "import json;print(len(json.load(open('$SCN'))))")
for i in $(seq 0 $((N-1))); do
  spent=$(cat /dev/null $OUTDIR/*.out.txt 2>/dev/null | awk '/^COST_USD/{s+=$2} END{printf "%.4f", s+0}')
  if (( $(echo "$spent >= $BUDGET" | bc -l) )); then echo "BUDGET STOP at $i spent=$spent"; break; fi
  id=$(python3 -c "import json;print(json.load(open('$SCN'))[$i]['id'])")
  [[ -s $OUTDIR/$id.db.json ]] && continue          # уже прогнан — повторный запуск продолжает с места остановки
  python3 -c "import json;json.dump([json.load(open('$SCN'))[$i]], open('$OUTDIR/_one.json','w'))"
  zsh $HERE/run_set_rec2.sh $OUTDIR/_one.json $PRIS $PORT $OUTDIR $DBF $BUDGET $MODEL $TEMP | grep -v '^DONE'
done
cp $SCN $OUTDIR/scenarios.json; rm -f $OUTDIR/_one.json
echo "DONE $OUTDIR spent=$(cat /dev/null $OUTDIR/*.out.txt | awk '/^COST_USD/{s+=$2} END{printf "%.4f", s+0}')"
