# Revision2 execution evidence

`benchmark_revision2.py native --freeze experiments/local_guards_ml_retrain/frozen_revision2 --output experiments/local_guards_ml_retrain/results/revision2/native --repeats 5` completed with exit0:151 methods,743 native trials/shards. Numerical runtime used OMP/OPENBLAS/VECLIB thread limits2. No single/load/scoring was run by this worker during the native command. CPU-clear was sent immediately on completion.

**Timing qualification:** the controller subsequently reported that a CPU-heavy independent closed2 audit started before its hold arrived and overlapped this native run. Therefore `results/revision2/native` is preliminary and **excluded from primary latency evidence**. Effects/status evidence remains retained. The entire first output and log are preserved unchanged.

A later coordinated quiet window may repeat native into a new `native-quiet` directory, followed sequentially by single/load after observation acceptance. This repetition is justified by known CPU contention, not result selection. No further timing has been run under the present instruction. Source/method files and closed2 gold/source/report/manifest were not opened or changed by this worker.
