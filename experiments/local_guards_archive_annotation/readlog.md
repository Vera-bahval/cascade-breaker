# Protocol drafting read log

- Read `experiments/local_guards_archive_comparison/POLICY.md`, `policy.json`, `schema.json` for native requirements, evidence and source-boundary contract.
- Read `data/collector-manifest.json` for archive inventory, source-binding and collector limitations. Its 2,074 P4 observations describe the collector inventory, not verification of the separate 542 representative selection.
- No case annotation, model calls, predictions, defender decisions/outcomes, existing annotations, report, methods, ML code, results, labels, or prior adjudication were read. No raw episode or supplementary retrieval was performed.
- `collector.py` search was attempted but `rg` was unavailable; no collector code was read. Split metadata was not needed for this protocol and was not read. Historical implementation was not independently rechecked; all native details here are scoped to the cited policy registry and must be checked per episode against supplied historical source/callable evidence.

## Mechanical reader

- Read `collector.py` lines 270–345 and matching line references to identify the actual `raw_context.events` representation and pre-cut collection; no case, label, prediction, outcome, or method was read.
- Implemented `inspect_case.py` as a mechanical reader over one supplied JSON; string values, including embedded JSON strings, are retained verbatim. `READER_USAGE.md` documents cursor semantics. Validation uses a temporary synthetic fixture only.
