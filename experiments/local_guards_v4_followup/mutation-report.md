# v4.2 mutation protocol

The harness is authored from policy and executable source before independent800
evaluation. No existing or new dataset, result, gold, ML artifact or research
report was opened while authoring it. The checks below use only tiny hand-authored
observations in `tests/test_mutations.py`; they do not establish corpus sensitivity.
There are no external API, inference, fitting or model calls.

## Fixed faults

| Mutation | Executable change |
| --- | --- |
| `no_currency` | In the private v3 payment evaluator, remove missing invoice/proposal currency obligations and the invoice/proposed policy-currency violation. Preserve schema checks and B01 ordinary approval-binding equality. |
| `human_every_amount` | Replace both `invoice > automatic` conditions with true when invoice amount is known, making missing independent approval unknown and proven false approval violated even below the automatic threshold. |
| `no_hold` | Set the private v3 evaluator's HOLD condition false, remove missing binding_hold obligation at P4, and remove the separate A05 approved-status HOLD condition. This covers P2 continuation, P3 approval and P4 payment. |
| `unknown_first` | Reverse UNKNOWN/known-violation priority in private v3 blocked/missing aggregation, the core requirement combiner and final core decision aggregation. |
| `no_origin_parent_binding` | In the private v4.2 proof wrapper, bypass origin compatibility/linkage and native parent/child/delegation tuple checks. Retain structural shape, prior-time, namespace/session/workflow, subject_matches, referenced IDs, source-family, value, material-version and target-call checks. This precisely scoped origin-and-parent removal is not wholesale provenance acceptance. |

Each mutation compiles an AST copy of the relevant real function into a private
globals dictionary. Cloned v3 functions also share their own private globals.
The harness neither rewrites guard inputs nor overrides predictions, expected
answers or module globals. The target methods are unchanged. Timing and evidence
are omitted from saved predictions so prediction bytes are reproducible.

## Interfaces

`mutate_guard(name)` returns the ordinary `guard(observation, policy=None)` API.
`configurations(profile)` returns five fixed evaluator-compatible method records.
`predict_rows(observations, profile="A", metadata=None)` returns evaluator-shaped
rows. Optional metadata supplies only identity/routing checks; it never repairs
the observation given to a guard. P5 has no autonomous decision and is no_check.
Malformed routing without usable canonical metadata is rejected.

```sh
/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python \
  -m experiments.local_guards_v4_followup.mutations \
  --observations INPUT.jsonl.gz --metadata METADATA.jsonl.gz \
  --predictions NEW-PREDICTIONS.jsonl.gz --receipt NEW-RECEIPT.json --profile A
```

`--metadata` is optional for valid routing. Both outputs must be new paths.
The receipt pins source, observation, optional metadata and completed prediction
SHA-256 values and records no gold/inference/fit use. Sources and inputs are
rechecked after writing predictions and before writing the receipt. Any later
label/scoring process must consume the completed, hash-verified predictions;
there is no score or gold argument in this CLI. Run A and B separately when both
profiles are wanted. This protocol contains no measured corpus mutation scores.

## Authored checks and acceptance boundary

```sh
/Users/proskurin-dmi/Documents/hw-itmo/cascades/experiments/local_guards/.venv-finbot/bin/python \
  -m unittest tests.test_mutations
```

Nine authored tests cover known/missing currency; missing/false low-amount human
approval; HOLD at P2/P3/P4 and absent HOLD evidence; UNKNOWN priority within payment,
within one requirement and across requirements; missing origin; wrong parent tuple;
retained foreign-scope rejection; unchanged target/input after mutation; malformed
envelopes; metadata routing without input repair; and a gzip CLI run with exclusive
outputs and receipt. Verification is limited to these authored source-contract
tests because opening corpus-backed tests is outside this author's read scope.
Independent800 sensitivity and separate scorer validation remain external steps.

## Read log

Explicit task source reads:

- `experiments/local_guards_v4_followup/POLICY.md`
- `experiments/local_guards_v4_followup/schema.json`
- `experiments/local_guards_v4_followup/policy.json`
- `experiments/local_guards_v4_followup/guard.py`
- `experiments/local_guards_v4/guard.py`
- `experiments/local_guards_v3/rules_v3.py` (source definitions only; v3 policy is not loaded)
- `experiments/local_guards_v4_followup/evaluate.py`, lines 1-285 only, for method configuration, prediction, routing and prediction-validation interfaces; no scorer or label files were opened.

The imported unchanged frozen guard additionally loads its own schema.json and
policy.json; the harness hashes both for provenance. The v4.2 guard loads its new
schema/policy. The test subprocess reads only these methods/configurations and its
own temporary authored JSONL. The harness reads and hashes its own source; the
tests and this report were authored locally. Source inventories were restricted
to evaluator/config/mutations filenames; no corpus directories were enumerated.

Instruction reads/checks: canonical `/Users/proskurin-dmi/Documents/igaming/AGENTS.md`;
AGENTS.md/CONTRIBUTING.md existence checks at cascades/research/followup ancestors
(none present); installed using-superpowers (subagent exclusion), Ponytail entry
and core, test-driven-development and writing-good-tests skill text. No native or
cross-project historical memory, archived chats or corporate sources were used.
