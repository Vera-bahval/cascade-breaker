#!/bin/zsh
# Tier 1 — уточняющий пакет прогонов (≥10 повторов, обе модели), чтобы доли стали с доверительными интервалами.
# Часть 1 «барьеры»: B,F,C,G × $10 100/$12 000/$50 000 — устойчив ли барьер $50k и $10k, те же ли правила на nano.
# Часть 2 «BEC»:     D,E   × $4 900/$12 000           — как часто Fraud ловит подмену реквизитов (D) против verified (E).
#
# Сначала посмотреть план и цену (бесплатно):   zsh code/finbot477/run_tier1.sh dry
# Запустить по-настоящему (~$2, ~1,5 ч):         zsh code/finbot477/run_tier1.sh
export LC_NUMERIC=C
HERE=${0:A:h}
DRY=""; [[ "$1" == dry ]] && DRY="--dry"
MINI=openai/gpt-4o-mini; NANO=openai/gpt-5-nano
run(){ echo "\n==== $* ===="; zsh $HERE/run_experiment.sh "$@" -v base -r 10 -x own -y $DRY; }

# ---- Часть 1: барьеры ($10 100, $12 000, $50 000) ----
for P in B F C G; do
  run -p $P -a 10100,12000,50000 -m $MINI -n bar_mini -b 0.7
  run -p $P -a 10100,12000,50000 -m $NANO -n bar_nano -b 0.3
done

# ---- Часть 2: BEC vs verified ($4 900, $12 000) ----
for P in D E; do
  run -p $P -a 4900,12000 -m $MINI -n bec_mini -b 0.5
  run -p $P -a 4900,12000 -m $NANO -n bec_nano -b 0.3
done

echo "\nГотово. Папки: code/runs/finbot477_bar_mini_t0_*, _bar_nano_t0_*, _bec_mini_t0_*, _bec_nano_t0_*"
