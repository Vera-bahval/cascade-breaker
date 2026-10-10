#!/bin/zsh
# Свой эксперимент на FinBot одной командой: профиль поставщика, суммы, варианты текста, бюджет.
# Сам подставляет порт и чистую базу профиля, собирает сценарии, показывает план и цену, спрашивает «запускать?»,
# гонит через run_pairs.sh (готовые счета пропускает — можно перезапускать) и в конце печатает сводку.
#
# usage: zsh code/finbot477/run_experiment.sh -p F -a 17500,20000,22500 [-v base,cfo|all] [-r 3] [-b 0.30]
#                                             [-n имя] [-x 15000|own] [-t 0] [-m openai/gpt-4o-mini] [-y] [--dry]
#   -p профиль A–G          -a суммы через запятую      -v варианты (base placebo cfo manager urgent nocheck | all)
#   -r повторы (3)          -b бюджет в $ на эту папку   -n имя эксперимента (по умолчанию custom)
#   -x текст счёта: ключ описания из пар (15000 — один текст для всех сумм) или own (у каждой суммы свой, как в парах)
#   -t температура (0)      -m модель (openai/gpt-4o-mini)   -y без вопроса   --dry только показать план
HERE=${0:A:h}; ROOT=${HERE:h:h}
P=""; AMTS=""; VARS=base; REP=3; BUDGET=""; NAME=custom; TEXT=15000; TEMP=0; MODEL=openai/gpt-4o-mini; YES=0; DRY=0
while (( $# )); do
  case $1 in
    -p) P=$2; shift 2;;   -a) AMTS=$2; shift 2;;  -v) VARS=$2; shift 2;;  -r) REP=$2; shift 2;;
    -b) BUDGET=$2; shift 2;;  -n) NAME=$2; shift 2;;  -x) TEXT=$2; shift 2;;  -t) TEMP=$2; shift 2;;
    -m) MODEL=$2; shift 2;;   -y) YES=1; shift;;   --dry) DRY=1; shift;;
    *) echo "непонятный параметр: $1"; sed -n 5,10p $0; exit 1;;
  esac
done
[[ -z $P || -z $AMTS || -z $BUDGET ]] && { echo "нужны -p профиль, -a суммы, -b бюджет"; sed -n 5,10p $0; exit 1; }
case $P in A|B) PORT=8766;; C|D) PORT=8767;; E|F) PORT=8768;; G) PORT=8769;; *) echo "профиль A–G"; exit 1;; esac
PRIS=$HERE/pristine/pristine_${P}_${PORT}.db
[[ -f $PRIS ]] || { echo "нет чистой базы $PRIS — соберите: zsh code/finbot477/build_pristine.sh $P $PORT"; exit 1; }
[[ -f $ROOT/.env ]] || { echo "нет .env с OPENROUTER_API_KEY в $ROOT"; exit 1; }
BUSY=0; PEERS=$(case $PORT in 8766) echo A B;; 8767) echo C D;; 8768) echo E F;; 8769) echo G;; esac)
lsof -iTCP:$PORT -sTCP:LISTEN >/dev/null 2>&1 && BUSY=1
pgrep -f "run_pairs.sh.*pristine_[A-G]_${PORT}.db" >/dev/null && BUSY=1

T_TAG=t${TEMP//./}; DATE=$(date +%Y%m%d)
EXP=$ROOT/code/runs/finbot477_${NAME}_${T_TAG}_${DATE}; OUT=$EXP/$P
if (( DRY || BUSY )); then SCN=$(mktemp -t scn).json; else mkdir -p $OUT; SCN=$EXP/scenarios_$P.json; fi
python3 $HERE/make_custom_scenarios.py --amounts $AMTS --variants $VARS --repeats $REP --text $TEXT --out $SCN >/dev/null || exit 1
N=$(python3 -c "import json;print(len(json.load(open('$SCN'))))")
TODO=$(python3 -c "import json,os;print(sum(not os.path.exists('$OUT/'+s['id']+'.db.json') for s in json.load(open('$SCN'))))")
SPENT=$(cat /dev/null $OUT/*.out.txt(N) 2>/dev/null | awk '/^COST_USD/{s+=$2} END{printf "%.2f", s+0}')
EST=$(echo "$TODO * 0.0068" | bc -l | awk '{printf "%.2f", $1}')
echo "Профиль $P (порт $PORT), модель $MODEL, температура $TEMP, текст: $TEXT"
echo "Суммы: $AMTS · варианты: $VARS · повторы: $REP → сценариев $N, осталось прогнать $TODO"
echo "Оценка: ≈ \$$EST (≈ \$0,0068 за счёт, ~15 с на счёт); уже потрачено в папке \$$SPENT; бюджет папки \$$BUDGET"
echo "Результаты: ${OUT#$ROOT/}"
(( $(echo "$SPENT + $EST > $BUDGET" | bc -l) )) && echo "Внимание: бюджета может не хватить — прогон остановится на лимите."
(( DRY )) && { (( BUSY )) && echo "Сейчас порт $PORT занят другим прогоном — запуск придётся подождать."; exit 0; }
(( BUSY )) && { echo "Порт $PORT занят другим прогоном (на нём профили: $PEERS). Дождитесь окончания."; exit 1; }
if (( ! YES )); then read "ans?Запускать? (y/n) "; [[ $ans == y* ]] || { echo "Отменено."; exit 0; }; fi
LOG=$EXP/log_$P.txt
echo "Идёт… следить: tail -f ${LOG#$ROOT/}"
cd $ROOT && zsh $HERE/run_pairs.sh $SCN $PRIS $PORT $OUT ${NAME}_$P.db $BUDGET $MODEL $TEMP > $LOG 2>&1
tail -1 $LOG
python3 $ROOT/code/summarize_run.py $OUT $SCN
