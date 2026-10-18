# SecJev4B runtime

Public SecJev v1.2.0 is pinned to `3ef7ecf0ec6af725c3bb295249dbb0ca8a2ef13c`; the checkpoint's calibration temperature is `1.334968103387446`. Backbone: `Qwen/Qwen3.5-4B-Base@1001bb4d826a52d1f399e183466143f4da7b741b`. The two backbone shard SHA256 values are verified by `scripts/bootstrap_secjev4b.py`, as are both released archives and Kev source.

Reproduction from the workspace root (the deadline must be the intended absolute experiment cutoff):

```sh
.runtime/mps-diagnostics/.venv/bin/python experiments/local_guards/scripts/bootstrap_secjev4b.py --workspace . --deadline-unix 1792043135.9469151
python3 experiments/local_guards/scripts/run_secjev4b_pipeline.py --deadline-unix 1792043135.9469151
```

Run the MPS supervisor with permission to access Apple Metal outside the restricted Codex filesystem sandbox; a sandboxed process reports MPS unavailable despite a supported macOS version. The first sandboxed load failed before any MPS inference and is preserved separately. Stop any other resident model before starting the supervised pipeline. No public or subscription inference API is used. CPU and MPS each run the three shortest and three longest distinct frozen inputs, with three repeats per payload; CPU reference precedes MPS. MPS uses Torch2.14 FP32, unmerged adapter, SDPA, GPU block triangular solver, no CPU fallback and no fast math. The final MPS runtime executes independent questions serially (question microbatch size 1) and empties the Metal cache after each question. CPU reference uses the original size-4 question batch. The numerical gate therefore explicitly compares CPU B4 against MPS B1. The initial MPS B4 partial measurements showed severe unified-memory pressure (driver25.32GB, long-call44–166s) and are preserved in `mps-batch4-partial.json`/`.log`; this is a runtime change, not a format or model change. Numerical tolerance is `1e-4`; chosen-answer flips and invalid answers fail the gate. The supervisor aborts scoring on a failed gate.

The score JSONL extends the existing normalized `secjev_batch.batch_row` schema with `format` and `payload_hash`. The legacy ablation field remains `plus_rationale`; evaluators must filter the new `format` field before fitting to prevent duplicate-prefix mixing. Format order is the exact old input, compact facts, relevant history. Only successful exact input-hash matches are resumed. Partial results and per-stage logs remain after the global deadline; the supervisor terminates an active model process at that cutoff.

Numerical checks are six selected payloads, not proof of parity on every input. The whole P4 dataset remains a small, scenario-grouped archive; confidence scores are question-answer probabilities, not harm probabilities.
