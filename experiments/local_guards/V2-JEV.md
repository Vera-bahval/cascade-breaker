# Canonical SecJev reruns

`cascade_guard.v2_jev` consumes the shared, label-free `v2_inputs.record`
contract. It renders precisely the shared `trusted_combined` natural-language
premise followed by the explicitly untrusted invoice and agent assertions.
It never reads evaluation labels or family IDs. The four applicability-aware
questions are frozen in source as `QUESTIONS`; all probabilities are new.

SecJev's official Noul head is **binary** (`false`, `true`). Both probabilities
are preserved without rounding. `UNKNOWN` describes runtime/context failures;
it is not a third learned head output. A question probability is not p(harm).

Use the pinned SecJev runtime environment, with `PYTHONPATH` set to
`experiments/local_guards`. Prepare one immutable input collection per model.
The 0.8B collection contains four actual checkpoints per episode; the 4B
collection contains only the final P4 checkpoint. Canonical record provenance
must contain `episode_id`, `stage_index` (0 through 3), and `cut_seq`.

```sh
.runtime/mps-diagnostics/.venv/bin/python -m cascade_guard.v2_jev --mode prepare --input COMMON.jsonl --output INPUTS.jsonl
.runtime/mps-diagnostics/.venv/bin/python -m cascade_guard.v2_jev --mode probe --model 0.8B --device cpu --input INPUTS.jsonl --output CPU-GATE.json
.runtime/mps-diagnostics/.venv/bin/python -m cascade_guard.v2_jev --mode probe --model 0.8B --device mps --input INPUTS.jsonl --output MPS-GATE.json --reference CPU-GATE.json
.runtime/mps-diagnostics/.venv/bin/python -m cascade_guard.v2_jev --mode batch --model 0.8B --device mps --input INPUTS.jsonl --output SCORES.jsonl --gate MPS-GATE.json
.runtime/mps-diagnostics/.venv/bin/python -m cascade_guard.v2_jev --mode features --model 0.8B --input INPUTS.jsonl --scores SCORES.jsonl --output FEATURES.jsonl
```

The pinned environment is Torch 2.14.0 / Transformers 5.17.0; the unrelated
`.venv-cheap` (Transformers 4.x) cannot load the Qwen 3.5 backbone. No
installation or API is required.
For 4B use `--model 4B`. Every probe/batch command holds the shared workspace
`heavy-model.lock`; CPU and MPS models are loaded in separate processes.
Do not launch concurrent heavyweight runs outside that lock.

The probe selects three shortest and three longest distinct inputs, runs each
three times, and checks A/A and CPU/MPS probability differences <=1e-4 with
unchanged answers. MPS batch refuses a failed or mismatched gate. All inference
is FP32, with the previously validated `solver_block` MPS correction. The 4B
MPS scorer processes questions serially and clears the Metal cache between
questions. No context is silently truncated; the existing limit is 8192 tokens.

Batch output is append-only and resumable by exact payload plus model identity.
Cached identical inputs record cache retrieval separately from original model
cost. Feature extraction checks score fingerprints and strict chronology.
Missing checkpoints yield explicit UNKNOWN for affected sequence blocks, and
never synthetic zero scores. Full sequence costs are reconstructed sums of
measured source calls; they are not a newly measured live monitoring latency.

The common input schema/adapter and source hashes must be frozen before
independent test scoring. Train selection and thresholds must be frozen before
unsealing labels. Old experiment files remain unchanged.
