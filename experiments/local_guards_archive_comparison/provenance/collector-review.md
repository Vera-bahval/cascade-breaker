# Independent collector, split and common-view review

Verdict: **changes required before fitting or selected-case inference**. The collector and split are acceptable within the current archived corpus; the reviewed common view leaks case identity and breaks consistent opaque identity across some raw and structured locations. Root has been notified and is repairing the view. This verdict does not certify the repaired artifacts until a focused readback.

## Important findings

1. **Serialized and arbitrary string fields bypass identifier normalization** (`views.py:35–60`, implementation reviewed before the root correction). Original invoice numbers remain somewhere in 4,877 of 5,410 view rows; 39 legacy rows retain label-bearing invoice identifiers. For example prefix `5627dcd26dd3be24cd3c8bd23caa` (`old/cle-clean_00-9cd83a`) retains `CLN-00-cle-clean_00-9cd83a` in `raw_context.events[32].model_output.tool_calls[0].arguments.query`. Serialized native `tool_result` strings likewise retain original invoice/account/namespace strings; 4,841 rows contain such obvious unnormalized invoice/namespace candidates. The view can therefore show an opaque invoice/account in facts beside its original value in raw evidence, as well as disclose archive case identity. Parse literal-safe serialized containers, normalize identifiers recursively and replace complete known identifier tokens throughout string fields, preserving monetary scalars and source claims.

2. **Vendor names and email addresses retain a different label-bearing identifier** (`views.py:14–24`). Full legacy run slugs survive in 569 rows from 317 episodes. Direct raw source `shadow-main.jsonl.gz#L175/steps/78` has company and account-holder name `Cascade Probe Vendor inj-base_pay_small-0cc6b9` and email `cascade-probe-inj-base_pay_small-0cc6b9@example.com`. The slug differs from the complete invoice number and namespace, so replacing those full identifiers alone does not repair it. Normalize native vendor identity fields and their embedded occurrences with consistent opaque aliases. Preserve actual industry, service and invoice-description evidence.

These are input construction findings, independent of any target labels or predictions. Neither a method nor DeepSeek has been inspected.

## Direct source checks and accepted properties

The reviewed native PR477 `fraud.py` signature and result use `recommended_action`; the corrected collector reads that exact field. Native hold/escalate notes and a successful child completion are distinct from invoice approval. The raw `TH639-r1` member at lines 30/34 confirms a typed hold plus a successful delegation; both remain visible.

Direct archive `TH601-r1` lines 45/47/50/51 establishes current invoice amount 1820 and proposed amount 1970.15 with the same native account. The collector preserves the amount contradiction and excludes the later transfer result from the P4 cut. Member SHA-256 is `4c6eb530bbe34f5dd1ddafa78359dc7cd0312127ee232b254cbd6a8087edf7b1`. `TH519-r1` lines 102/103 establishes latest same-invoice history amount 4200 followed by a failed Fraud return; completion is false, with the failed summary retained. Member SHA-256 is `de591143b2fa1b5fb1cc68cef552e0c75803919987911b2312f90108f01efad9`.

Direct legacy `shadow-main.jsonl.gz#L175` steps 76/78/80 establishes current amount/account 800/native account versus a proposal of 920/different account. Initial transaction emptiness is actually present in `db_initial`; `db_final` is separate. The collector reads initial fixtures and prefix events, rather than filling state backwards from final outcomes. The transfer proposal is pre-result evidence, not proof of execution or harm.

A direct pairing scan over all registered tar hook episodes found zero unpaired nondelegation returns using tool, arguments, workflow and session agreement. The current code nevertheless ingests a nondelegation result even if `paired` is false (`collector.py:339–359`); this is a nonblocking current-corpus limitation, not a demonstrated contaminated row. A foreign-workflow normal getter could overwrite same-ID state in a changed malformed input. The Fraud pairing gate itself rejects mismatched completion.

The split preserves indivisible repeat/control/executor groups. Current allocation is 58 representative and 29 challenge groups of 289; remaining groups split 151 TRAIN and 51 CAL, with Luna removed from both development packages. Direct scenario-ID inspection found no recognized base/control aliases crossing groups. The fixed challenge selection uses predeclared mechanisms and no target prediction. This is 30 percent of groups, not episodes, and the previously exposed archive is not a blind generalization test.

The 2,074 P4 rows consist of 2,051 before-tool hooks and 23 explicit `recorded_model_proposal` cuts. Retain this distinction in reporting; none proves a completed transfer. Historical/instrumented modes differ only by declared technical links, and replay is not recovered executor authorization. Native numeric IDs remain join-only and must stay excluded from ML features.

## Acceptance limits

The parent reported successful collector/split/view tests and whole-artifact schema, causal-sequence and business-equality checks for all 10,820 rows. They were not redundantly rerun. This review instead inspected source implementation, original archive bytes, identity exposure and split aliases. It does not replace independent gold adjudication or assert arbitrary malformed-input correctness. No API, executor, source edit, target method, prediction or commit was used. Only this review and its JSON receipt were written.
