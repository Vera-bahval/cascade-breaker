# Original-v1 accounting rescores

Execution only. No learned source/model/threshold edits, inference reruns or
original-output overwrites. Both rescores used approved `evaluation_revision2.py`
with `--model-freeze experiments/local_guards_ml_retrain/frozen` and bootstrap1000.
All original-v1 defective-binding qualifications remain applicable.

Archive reused `results/original-v1/{archive-ml,archive-controls}` and original
`local_guards_v4/data/{observations,metadata,gold-actions,gold-outcomes}.jsonl.gz`,
adding `--episodes experiments/local_guards_v4/data/episodes.jsonl.gz`.
Output: `results/original-v1-corrected-accounting/archive-scores`; exit0.

CAL reused `results/original-v1/{cal-ml,cal-controls}` and unchanged
`cal-inputs/{observations,metadata,labels}.jsonl.gz`, with `--split CAL` and explicit
`--episodes results/original-v1-corrected-accounting/cal-registry/episodes.jsonl.gz`
(all paths relative to `experiments/local_guards_ml_retrain/` where shortened).
Output: `results/original-v1-corrected-accounting/cal-scores`; exit0. CAL outcomes
remain unavailable as in original CAL scoring; no outcome file was added.

`cal-registry/receipt.json` documents the independent combined universe: CAL archive
registry IDs prefixed exactly `archive:` as in prepare(), plus synthetic episode
IDs copied verbatim from prepared CAL metadata. No source intent was inferred.
The registry adds the two no-prefix CAL archive members
`archive:old/cle-clean_00-9cd83a` and `archive:old/cle-clean_02-efe42c`.

| Readback | Archive | CAL |
| --- | --- | --- |
| All-slice methods |222|222|
| Full episode registry |3378|2727|
| Episodes with observation prefixes |3373|2725|
| Episodes without prefixes |5|2|
| Full A/B unassessed episodes |5|2|
| Payment unassessed episodes |1327|1385|
| Known / unknown outcomes |2069 /1309|0 /2727|
| Actual-harm / completed-transfer count |114 /2067|unavailable|

All-registry interruption rates are null where legitimate episodes are unassessed;
explicit lower/upper bounds preserve the distinction between no guard evidence,
observed UNKNOWN and known STOP/no STOP. No-prefix outcomes create no guard credit.
Calibration eligible/safe counts remain payment1342/616, A2725/787, B2725/501.

For every method and every slice, `actions`, `reached_actions`, `episodes` and
`calibration_constraints` match original-v1 outputs exactly. Corrected accounting
changes the external episode-universe reporting only. All new score artifact-hash
tables match. Full readback is `execution-checks.json`, SHA256
`2b7a22a6a2d4123be6e00afbae2947ae6554acb6ec3259f6bcafaeb08c1d895d`.

Revision2's first native run is separately recorded in
`results/revision2/execution-report.md`: preserved preliminary evidence excluded
from primary latency because the controller reported concurrent CPU-heavy audit
activity. No new timing, single/load or closed2 file reads were performed after
that qualification. Both accounting rescores are now complete; no compute remains.
