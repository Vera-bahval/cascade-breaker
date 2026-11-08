# Scoped label clearance

**PASS_SCOPED_LABEL_CLEARANCE** on the exact SHA-256 snapshot recorded in `labels-clearance.json`. The original `labels-review.md/json` and source proposals are preserved.

The regenerated labels contain all 5,410 canonical rows. TRAIN has exactly 1,512 and CAL exactly 556 rows, matching final split metadata, with no selected or Luna membership. Every scenario label and its full provenance equals the original 3,378 reviewed episode proposals. Canonical native_core recomputation matches every stored label. Labels manifest source and input hashes match current files.

Native core decisions: {'ALLOW': 4599, 'BLOCK': 788, 'UNKNOWN': 23}. Scenario decisions: {'ALLOW': 1745, 'UNKNOWN': 2858, 'BLOCK': 807}. Unknown source annotations and all four original-oracle conflicts remain unknown. The original fixed historical 112/846 target remains a separate axis.

The revised workflow reference binds paired Invoice and Fraud events to native invoice/vendor arguments, requires native task_status success, uses the latest matching completed Invoice and Fraud, and checks Invoice completion before Fraud start. Known absent/failed required completion blocks payment progression; missing/incomplete evidence is unknown. Recorded model-proposal overlap remains unknown rather than proof of a violated execution order. Seven focused workflow checks and three repository reference tests pass. Malformed operand/decimal checks are included in those tests and the preserved earlier 12-case recheck.

Both common views contain 5,410 rows. Recomputing native_core on every historical and instrumented common-view row produces 0 changes from stored gold. View script and manifest output hashes also match. This verifies label invariance under the common identifier/evidence representation.

This clears the scoped reference-label/package fixes. It does not adjudicate native semantic fraud/exception/tax safety, invent unknown source targets, establish archive harm, or certify production authorization. No fitting, predictions, external calls, data edits or commits were performed.
