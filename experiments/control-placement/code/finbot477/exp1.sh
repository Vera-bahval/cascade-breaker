#!/bin/zsh
SP=${0:A:h}   # вспомогательные скрипты и данные — в этой папке
BASE=${0:A:h:h}/runs/finbot477_exp1_profiles_$(date +%Y%m%d_%H%M%S)
for prof in A B C D; do $SP/run_set.sh $SP/exp1_scenarios.json $SP/pristine/pristine_${prof}_8766.db 8766 $BASE/$prof exp1.db 0.27; done
echo "EXP1 DONE $BASE"
