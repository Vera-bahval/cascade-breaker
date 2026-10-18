# Archive latency v2 source review

SOURCE_REVIEW_PASS. Public synthetic fixtures only; profiler not run on actual archive/models. Frozen MF05/addon/completion runner unchanged.

The v1 provenance gaps are fixed: exact authorized COMPLETE/path/status and root-plan SHA are required, and METHODS is anchored to the successful pipeline seal. Seven profiler plus six report presentation tests pass. Exact hashes are recorded in ARCHIVE_LATENCY_SOURCE_REVIEW_V2.json.

Hash sampling is label-independent. Warm singleton head prediction includes its own preprocessing; cached source costs remain separate, and source+head is an explicit reconstruction rather than live end-to-end latency. Missing measurements and unmeasured per-model memory remain explicit.

The 300-second budget is cooperative, capped by the original global deadline. Individual model load/predict calls cannot be interrupted in-process; caller needs a hard process timeout for a strict maximum. No deadline extension or automatic profiler launch is authorized by this review.
