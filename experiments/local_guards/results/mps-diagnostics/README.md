# SecJev MPS diagnosis and candidate runtime

Confirmed on this Apple M3 Pro host, 2026-10-14. Original CPU batch and its Torch 2.6 environment remain unchanged.

## Root cause

The pinned Qwen3.5 PyTorch fallback calls `torch.linalg.solve_triangular` on tensors shaped `[questions, heads, chunks, 64, 64]`. The Torch 2.6 MPS implementation uses only the first dimension to count matrices. In this test it processes 4 matrices instead of 512. Remaining result entries are uncomputed and depend on allocation history. Real model inputs already disagree at the first DeltaNet solve; the first four comparisons against an identical CPU solve have absolute errors up to 35.18.

A synthetic reproduction with the real dimensions has 99.21% of values wrong by more than 1e-4. Flattening the three batch dimensions before the old native solve fixes that synthetic error (maximum 3.34e-6). Torch 2.14 computes the product of all batch dimensions and fixes the real model output without a mathematical-model change.

Primary source lines: [Torch 2.6](https://github.com/pytorch/pytorch/blob/v2.6.0/aten/src/ATen/native/mps/operations/LinearAlgebra.mm#L650), [Torch 2.14](https://github.com/pytorch/pytorch/blob/v2.14.0/aten/src/ATen/native/mps/operations/LinearAlgebra.mm#L1477).

## A/A and parity

- CPU reference service: two full FinBot states, three repeats each; identical probability distributions.
- CPU separate fresh processes: three reloads, two full states, three repeats; all 18 valid, differences within and across reloads exactly zero.
- Old Torch 2.6 MPS: three fresh processes, two full states, three repeats; only the first input in each process produces a finite but incorrect result. Remaining 15 of 18 return UNKNOWN from nonfinite distributions. Eager attention plus disabling shape bucketing gives finite but incorrect results and does not fix the solver.
- Torch 2.14 native MPS: two states, three repeats; all six valid, maximum CPU probability difference 2.57e-6, identical repeated distributions.
- Torch 2.14 plus GPU block inverse: nine original real prefixes, three repeats, then two further fresh-process reloads of two states each. All 39 valid, maximum probability difference from CPU 7.69e-6, no categorical or threshold flips (0.5, 0.75, 0.9, 0.95, 0.99), exactly identical within and across reloads. Strict gate was 1e-3.

The model is eval-only and every parameter is FP32 on mps:0. MPS fast math is explicitly disabled. The block inverse executes GPU tensor operations and does not perform CPU fallback. Only tokenizer/preparation and final JSON conversion use CPU as usual.

The native new MPS solver is correct but slow. A GPU block inverse addresses the same bottleneck [reported for Qwen3.5 decision models](https://github.com/pytorch/pytorch/issues/198304). The local prototype patches only the Qwen module's torch view; installed sources/global torch are unchanged. Probability agreement is independently verified above.

Warm full-state MPS block inference was 1.74-3.57 seconds, median 2.60 seconds, on the nine-prefix panel. Peak process RSS was 4.28 GB and MPS driver allocation 5.47 GB. An archive CPU batch was active during this diagnostic, so these observations are not isolated throughput benchmarks. Do not infer a universal speedup or a statistical safety guarantee from this small parity panel.

Raw distributions, errors, timing, memory, package versions, fingerprints and request hashes are in the JSON files. `summary.json` summarizes them; `sources.json` contains related primary reports and the boundaries of their applicability. `reload-suite-commands.json` records the actual subprocess commands.

## Reproduce

From the workspace root:

```sh
PYTHONPATH=experiments/local_guards .runtime/secjev/.venv/bin/python -m cascade_guard.mps_solver_repro --output experiments/local_guards/results/mps-diagnostics/torch26-solver-repro.json
PYTORCH_MPS_FAST_MATH=0 PYTHONPATH=experiments/local_guards .runtime/mps-diagnostics/.venv/bin/python -m cascade_guard.mps_diagnostics --device mps --patch solver_block --output experiments/local_guards/results/mps-diagnostics/reproduced.json
PYTHONPATH=experiments/local_guards .runtime/mps-diagnostics/.venv/bin/python -m unittest discover -s experiments/local_guards/tests -p 'test_mps_diagnostics.py'
```

The isolated environment pins Torch 2.14.0, Transformers 5.17.0 and PEFT 0.21.0. Full resolved dependencies are `.runtime/mps-diagnostics/requirements.lock.txt`. Existing verified 0.8B checkpoints and pinned Kev source are reused read-only.

A separate resident loopback service can be started after diagnostics complete:

```sh
PYTORCH_MPS_FAST_MATH=0 PYTHONPATH=experiments/local_guards .runtime/mps-diagnostics/.venv/bin/python -m cascade_guard.mps_diagnostics --device mps --patch solver_block --serve-port 8012 --output experiments/local_guards/results/mps-diagnostics/service.json
```

Its `/health`, `/score` and `/v1/systemone` contract inherits the reference service; all full-state+branch token limits and UNKNOWN rules are preserved. `--output` is unused in service mode; service metadata and fingerprint are emitted on stdout and `/health`. Always write a new score artifact and use the new model fingerprint; do not append MPS results to a CPU-score file.

## SecJev-2B bounded comparison

SecJev-2B is the actual released security checkpoint [v1.1.0](https://github.com/UESTC1010/SecJev/releases/tag/v1.1.0), not generic Kev. Verified backbone: Qwen/Qwen3.5-2B-Base@b1485b2fa6dfa1287294f269f5fb618e03d52d7c. Its own bounded CPU/MPS diagnostics and verified download provenance are in `secjev2b/`.

The text-only loaded model has 1,899,693,376 parameters. On this 36 GB host it loaded and ran in FP32 on both CPU and MPS. Three identical full states with the same four questions were scored three times each on each backend: 18/18 valid, A/A distributions exactly identical. CPU2B versus MPS2B (Torch 2.14 + GPU block inverse) maximum probability difference 9.0003e-6; no categorical or threshold flips.

CPU2B took 18.85–27.50 seconds per four-question request (median 23.55 seconds). MPS2B median was 4.23 seconds; excluding the first request for each case, median 3.77 seconds. MPS peak RSS 7.04 GB, parameter allocation 7.61 GB and driver allocation 9.67 GB. The original CPU archive batch was active, so these are contended observations. The final idle-client matched comparison is recorded below; these earlier CPU2B numbers remain labeled contended.

The 2B checkpoint changes the probabilities as expected from a different model. These differences are kept separate from numerical parity against the same 2B CPU reference. FinBot detection quality still needs the full grouped evaluation; three smoke cases cannot establish whether 2B is more accurate.


## Final matched-input speed comparison

Both archive batch clients were paused; the original CPU batch had completed all 392 P4 rows and both services finished their in-flight requests. No other heavy fits ran. Each of three full states was warmed once per arm, then scored three times with the same four questions. CPU and MPS calls were serial. The two 0.8B services remained loaded; the 2B model was loaded in a fresh short-lived MPS process after the 0.8B measurements.

| Arm | Median of nine warm compute times | Valid requests |
|---|---:|---:|
| SecJev-0.8B CPU, Torch 2.6, FP32 | 5.063 s | 9/9 |
| SecJev-0.8B MPS, Torch 2.14, FP32, block solver | 1.535 s | 9/9 |
| SecJev-2B MPS, Torch 2.14, FP32, block solver | 2.895 s | 9/9 |

Per-state 2B MPS versus 0.8B CPU speedups were 1.41x, 1.71x and 1.80x. Per-state 0.8B MPS versus 0.8B CPU speedups were 2.64x, 3.54x and 3.39x. Global median ratios are 1.75x and 3.30x respectively. Thus the proposed larger 2B model on MPS did beat 0.8B on CPU for these three matched states; 0.8B on corrected MPS was faster still. This is a small single-host benchmark, not a general latency guarantee.

All same-model CPU/MPS comparisons passed the strict numerical gate. 2B distributions were exactly identical across its two independent MPS process loads. Full raw warmups, three-repeat distributions, compute/HTTP/queue times, metadata and input hashes are in `paired-speed-idle.json`.

Separately, all 392 P4 prefix/ablation rows from the actual CPU and MPS batches matched: maximum probability difference 1.69277e-5, zero categorical or tested threshold flips and no UNKNOWN. The paired artifact is `../secjev-p4-cpu-mps-parity.json`. After the speed benchmark the full 1732-row MPS batch was resumed with the same service fingerprint, preserving separate CPU and MPS score files. The complete GPU archive evaluation remains owned by the parent task.
