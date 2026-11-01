#!/bin/zsh
SP=${0:A:h}   # вспомогательные скрипты и данные — в этой папке
OUT=${0:A:h:h}/runs/finbot477_ours_rep2_$(date +%Y%m%d_%H%M%S)
$SP/run_set.sh $SP/our_scenarios.json $SP/pristine/pristine_C_8767.db 8767 $OUT exp2.db 0.95
echo "EXP2 DONE $OUT"
