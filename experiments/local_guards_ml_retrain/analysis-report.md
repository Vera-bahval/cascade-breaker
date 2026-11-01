# Analysis/report task evidence

Status: DONE. All-input postprocessing, archive interval correction, prose and
final source/numerical readback are complete.
No commit was made by this worker. Main `experiments/NO_LLM_REPORT.md`, all frozen
sources/models/thresholds and all input observations/gold remain outside edits.

## Scope and chronology

The authoritative brief was read first. The controller explicitly released
closed2 after prediction commit `b7afad7c7e2982fa95512d13bb2077e3c85c7b2a`.
During the coordinated quiet native/single/load window this worker performed
only file/source reading and text/code editing. No Python, tests, corpus parsing
or calculations ran until the controller's explicit CPU-CLEAR. The preliminary
native result is excluded; the quiet replacement is retained without any new
timing by this worker.

Read the full humanizer-ru SKILL and PATTERNS before Russian writing. The
lightweight native memory lookup was used only for earlier reporting cautions
(formal contracts, missing proof, native atomicity); numerical claims come from
current files. No external API, network source, fitting, threshold selection,
subagent, commit or historical raw-archive expansion was used.

## Analysis implementation

`analysis.py` uses the standard library and saved post-freeze artifacts only.
Every consumed source is recorded in `analysis/source-hashes.json`; prediction
receipt hashes are bound to the pre-release commitment. It checks prediction
shards/coverage, final gold identity, independent overlap counts, score artifact
hashes and exact per-method counts against the authoritative scorer. All
contracts/arms/seeds/raw/gated and separate argmax diagnostics remain represented.

Full/common duplicate memberships and dependency components reuse the independent
review, with reuse explicitly certified by the final re-review. The separate
supplied-baseline payment normalizer is reproduced without importing the
side-effectful reviewer or invoking any target method. Its results match exactly:
460 payment rows,148 unique; development315 unique;61 shared unique,302 shared
rows. The total31 components become30 preventive full-contract components and
one payment component. A single-component interval is unavailable, not a fake
zero-width confidence interval. Outside-dev safe-stop FPR is null because this
slice has no gold ALLOW.

Raw/gated operating points have separate CAL thresholds. The gate attribution
table compares each gated result to its own stored pre-gate decision, so the
reported gate contribution does not conflate different selected thresholds.
All action counts retain malformed-time cases; episode/first-STOP/prevention
columns preserve the scorer's unavailable-order semantics.

## Commands and checks

Executed after CPU-CLEAR from `research/finbot-general-guards`:

```sh
/usr/bin/python3 experiments/local_guards_ml_retrain/analysis.py \
  --bootstrap 1000 --output experiments/local_guards_ml_retrain/analysis
```

The first run was explicitly partial because new scoring outputs were pending;
it listed every missing input in `summary.json`. It produced2175 sensitivity
rows and8196 existing diagnostic score rows. It did not repeat inference or
timings. The final run and its acceptance result are recorded below when ready.

An inline standard-library check imported only `analysis.py` and asserted a
four-row own fixture:4 eligible,1 correct decisive,1 false ALLOW,1 safe STOP,
2 UNKNOWN,1 checker exception and0 classifier-only UNKNOWN. Reciprocal duplicate
weights gave eligible mass3, correct mass0.5 and safe-stop FPR2/3. The component
bootstrap used three own components. An independent overlap check reproduced
the exact five counts above. Output: `PASS`.

After the sensitivity/serialization changes, a targeted standard-library fixture
checked that a single connected component returns an unavailable interval with
zero executed resamples, not identical low/high endpoints. Two generated gzip
CSVs with different destination names had identical bytes; Unicode and nested
JSON columns round-tripped through `gzip.open`/`csv.DictReader`. Output: `PASS`.
The large derived CSVs use gzip directly; earlier plain generated copies were
compressed, decompressed SHA256-verified and removed, reclaiming about90MiB.
No raw/scored/frozen evidence was removed by this worker.

After both authoritative new-test score outputs completed, an independent
standard-library comparison checked219 methods in each assessment. For every
method it matched eligible/correct-decisive/UNKNOWN, both false-ALLOW types,
safe denominator, gate-change count and safe-stop numerator. Both comparisons
passed. Score inputs preserve1200 registry episodes,1180 general actions and460
payment actions;15/3 actions respectively have unavailable event ordering.

CAL readback initially attempted the stronger assertion that frozen `feasible`
equals new scorer `satisfies`. It failed immediately on
`payment_v3__old__archive__logistic__17__raw`: False versus null. Investigation
showed the documented stricter order policy applies to eight CAL episodes in
every method. This was not hidden or repaired in the scorer. A second check
passed for all144 frozen model/variant records on eligible/safe episode counts,
safe STOP and reached false ALLOW counts. The full safe denominator is ordered.
All144 calibrated variants and3 unchanged rules also have zero false ALLOW
across ALL eligible actions, which bounds false ALLOW at zero for any ordering
of those saved actions. This bound does not restore first-STOP/prevention or
override the strict full-replay null. `cal-reconciliation.json` preserves both
statuses and the bound.

### Explicitly authorized two-state feature diagnosis

The controller separately authorized extracting the complete frozen old/new
feature vectors of only `r2c-0524` and `r2c-0525`, to verify the proposed
representation counterexample. No model prediction, training, gate reevaluation
or method repair was done. The exact executable was:

```sh
/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python
```

The inline command imported `features_revision2.features`, loaded those two
released rows by prefix ID, evaluated `features(row, 'old')` and
`features(row, 'new')`, compared complete dictionaries and SHA256 of sorted JSON,
and wrote `analysis/pair-feature-diagnostic.json`.

Both old38-feature vectors match (`d038ee459d1a36be0f53f095273b03725915e5685eb6422fcbe271933ed0c8e2`).
Both new472-feature vectors match (`c12a377e39565e91573ecbda86adbc23a8a23b0c69378e4c6c76502aad5687ed`).
Recursive observation comparison found only clearance sequence40/25, its
administrative record ID and prefix ID differing; HOLD sequence is30. The first
state belongs to the14 initially ambiguous projection rows; the second does not.
This is a limitation of this frozen representation under the predeclared strict
HOLD chronology interpretation, not an intrinsic limitation of ML or a claim
that native FinBot documents this sequence comparison.

## Current evidence-based findings

Primary seed17 has only two CAL-feasible ML operating points, both payment gated:
old/mixed CatBoost and new/mixed LR. New-test decision coverage is269/460 and
110/460; false ALLOW1/17, safe STOP12/212 and138/212. The payment rule reaches
347/460 with0 false ALLOW and0/212 safe STOP. Raw calibrated models all abstain;
full-contract models all abstain after no feasible CAL-grid pair was found.
General rules also violate the CAL safe-stop bound. New features do not show a
stable improvement; richer data can improve diagnostic argmax coverage while
retaining unsafe decisions. No test-driven model/seed selection is performed.

At fixed gated thresholds the proof gate removes9/52 false ALLOW proposals
respectively, interrupts no additional safe states and earns no correct BLOCK.
Outside the14 temporal-projection sensitivity rows, all1/17 false ALLOW remain.
Payment view balancing changes old/mixed CatBoost coverage58.48% to35.14%; all
212 safe payment rows are among the302 rows overlapping development states.

Native ScriptClient ownership was checked directly in
`benchmark_revision2.py::native_trial` and
`local_guards_v4/tests/test_runtime.py::ScriptClient`. Predetermined requests
replace model responses; actual FinBot handlers/delegations/local MCP run.
The report never represents this as a Luna, adaptive LLM or live money-saving
experiment. SystemUtils is simulated; source trust, ABA, sidecar transactions
and complete native writer coverage remain limitations.

## Final all-input acceptance

Final analysis command exited0 with29291 score rows,2175 sensitivity rows and
no missing inputs. The retained native diagnostics are included:151 native
method entries,147 single-call methods and72 cold model processes. Generated
full tables are embedded in APPENDIX and remain reproducible as analysis/tables.md.
All9 main-table rows were numerically checked against primary scores and timing
summaries. The report is1000 words including its table.

A late concrete grouping concern required separate postprocessing. The immutable
scorer prefixes global archive group_id by source. Exact command:

```sh
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 VECLIB_MAXIMUM_THREADS=2 /Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python experiments/local_guards_ml_retrain/archive_intervals.py --bootstrap 1000 --output experiments/local_guards_ml_retrain/analysis/archive-global-intervals.json
```

Exit0:51 primary seed17 raw/gated/rule modes corrected; every point-summary
section exactly matches the original scorer. Payment clusters517 become298;
full-contract clusters561 become308. Only local analysis rows use exact global
metadata.group_id. No source/scorer/model change, fit, unpickle or inference.
Corrected intervals supersede these51 all-source intervals; all other original
archive source/split/seed/diagnostic intervals are withheld from report claims.
New1200 component intervals remain separately30 preventive components/1 payment
component; the latter is unavailable rather than zero-width.

Own immutability readback passed8 baseline protected files including mainreport
SHA b00761a7cd92c7bbaaf7b9234776ddb7a1b2dc31a46cdea294738b015041f1e5.
Original freeze361 members/11 source files and revision2 freeze434 members/17
source files,72 models each, match their manifests. See protected-inputs-readback.
Parent also confirmed complete original archive raw restoration from exact Git
blobs and zero protected-path differences against the baseline.

Final verification.json records source checks, numerical table readback,
coverage counts and output hashes. Source identities are in source-hashes.json
and archive-global-intervals.json. All source/coverage/numerical assertions
passed before a final word-count check found1003 words; three prose words were
removed, then word-count/style/embedded-table checks passed. No numeric table
or analysis input changed in that trim.

Parent owns the commit and final independent audit. This worker stops writes
after handing off these verified artifacts.
