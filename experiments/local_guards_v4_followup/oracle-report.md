# Independent v4.2 policy oracle

`oracle42.py` implements `adjudicate(observation, profile="A", enabled_requirements=None)`.
It returns an aggregate ALLOW/BLOCK/UNKNOWN, all twelve requirement IDs mapped to
satisfied/violated/unknown/not_applicable, requirement-level reasons and a boolean
malformed flag. Disabled
or out-of-profile requirements are not_applicable. Unknown configuration IDs raise
ValueError; malformed observations return global UNKNOWN with malformed=true.
All normal results, including unknown facts and audit P5, return malformed=false.

This is an independent reference for open and conditional replay and a later
cross-check of separately authored future gold. It is not the target guard, does not
import or call that guard, and does not make guard output into gold. It has not been
used to author the independent future corpus. No corpus, gold, saved predictions,
target tests or target implementation were read.

## Sources actually read

- This experiment's PLAN.md and provenance/implementation-brief.md.
- This experiment's POLICY.md, policy.json and schema.json: semantic obligations,
  business registry, exact callable matrix and structural envelope. POLICY.md was
  published and read before finalization, with no target-code access.
- Frozen `experiments/local_guards_v4/POLICY.md`, including the proof semantics,
  stage applicability and explicit native-currency limitation.
- Frozen `experiments/local_guards_v4/prepare_data.py` source, initially lines 1–260;
  that broad source read included loader code but no loaded files/data. The subsequent
  source read was limited to `oracle` (lines 143–213). No old guard/runtime/store was read.
- Frozen `experiments/local_guards_v3/prepare_data.py:action_gold` (lines 396–468),
  for the separately written payment predicate reference. No rules_v3.py was read.
- Project instructions and local skill instructions. No native/long-term memory,
  historical chats, model API, external service, native FinBot source, dependency
  installation or target/future files were used.

The implementation is written independently in ordinary Python and uses only the
standard library. The old action oracle is a policy reference, not an imported
dependency. Its simplified trust assumptions are not reused: this reference validates
the v4.2 proof envelope before applying business predicates.

## Interpretation fixed before closed evaluation

1. Structural errors anywhere in the envelope cause global UNKNOWN. Within a
   structurally valid envelope, an applicable proved violation outranks unknown facts.
   A known non-USD proposal is a currency violation even if invoice currency is unknown.
2. Select newest same-scope prior evidence before origin/value/version validation.
   A missing/invalid origin, missing record ID, mismatching value or stale current
   version at the newest sequence does not resurrect older evidence. Equally recent
   conflicting attestations make the fact unknown. Future and unrelated-scope evidence
   does not establish a current fact.
3. Material facts retain frozen v4.1 version semantics: require invoice_version when
   an invoice is in context and vendor_version when a vendor is in context. This is
   deliberately not relaxed by fact family. HOLD and human clearance remain exempt
   from material version equality while retaining scope, subject, time and latest-event
   checks. A material edit does not erase a proved HOLD.
4. Origins are explicit. Server snapshots require snapshot_id and server_context or
   native_tool; native tool results require source_call_id. Generic declared typed
   fixtures use initial_fixture. Human facts use independent_registry exclusively.
   Missing new origin metadata is an unknown fact, not an upgraded legacy proof.
   Review and HOLD are not native DB fields: server_snapshot is invalid for both,
   including source=native_tool. Their actual typed-history evidence uses tool_result
   with its producing call ID, or explicit declared fixture/independent registry.
5. Native Invoice currency is absent. A native snapshot or tool result never proves
   invoice currency. Accept explicit initial fixture, independently registered currency,
   or declared_fixture/server_context/currency_contract_attest bound to current
   material versions. USD policy is only a constraint, never an observed currency.
6. A04 requires actual context parent_workflow_id, delegated_workflow_id and
   delegation_call_id and exact equality of that tuple in the proof. Parent and child
   IDs may be equal. Context workflow_id remains the admitted B02 owner; it is not
   replaced by either native parent or child ID.
7. P3 approval requires known canonical current status, positive amount within the
   maximum, active vendor and resolved HOLD. Later fraud/transfer evidence and the
   P4 human threshold are not required at that earlier cut. A09 retains only legacy
   known early vetoes. A07 checks bookkeeping reference after transfer; it does not
   treat the already completed matching transfer as a forbidden second transfer.
8. B binding and claim records are trusted producer snapshots. This oracle can check
   their declared identity, material fields, owner, active state, key and prior time;
   it cannot establish native atomicity, current generations omitted by the producer,
   complete external-write coverage or provenance authenticity from JSON alone.
   B01 compares the ordinary approval binding to the proposed transfer's normalized
   amount/currency and current context IDs, versions and account, independently of
   A08's validated invoice-fact readiness. Missing comparison inputs make B01 unknown.
   When its comparison inputs are available, a present approval record at or after
   the cut violates B01. A present claim at or after the cut violates B02.
   A same-owner vendor-wide claim covers both
   that vendor and its invoices. An invoice claim only covers its exact invoice.
   A present claim cannot be matched to a missing namespace and violates B02.

## Verification

Command: `python3 -m unittest discover -s experiments/local_guards_v4_followup/tests -p test_oracle.py -v`

19 authored synthetic tests passed after source-contract readback. They cover complete
payment, optional/required human evidence, native snapshot and tool-result origins,
explicit currency, invalid-origin/latest/stale/conflicting evidence, both material
versions, persistent HOLD and later independent clearance, strict precedence,
malformed input, native equal parent/child IDs, early approval applicability, B01/B02/B03,
vendor-wide owner coverage, present-record ordering, missing claim namespace,
explicit malformed flags, and audit P5. These are contract examples, not evidence of corpus-wide accuracy or
independence of any later gold labels.

Final v4.2 POLICY readback: completed. Its explicit parent/call, status, dispatcher
attester, A07 shape and A09 applicability obligations are implemented. The parent
coordinator additionally clarified the review/HOLD snapshot exclusion before the
independent closed corpus was generated. The separate policy author added the
explicit native-derived snapshot allowlist and review/HOLD exception; that canonical
paragraph was read back before delivery.

The coordinator's later pre-freeze clarification of B01/B02 present-record ordering,
native vendor-wide coverage and missing namespace handling was implemented only from
the contract instruction. Three new authored tests first failed under the previous
interpretation and then passed with the clarified oracle. No target/dataset access
was added for that clarification. POLICY.md remains owned by the coordinator.
The final pre-freeze B01 clarification uses proposed transfer amount/currency rather
than validated invoice facts; missing B01 comparison inputs are unknown before its
record ordering is assessed. A new authored test failed before that contract-only
change and passed afterward. This separates B01 from A08 proof readiness.
