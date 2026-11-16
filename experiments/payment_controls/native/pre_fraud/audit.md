# Independent PRE-Fraud adjudication

The final reference in `gold.json` covers 56 first proposed calls from eight
native diagnostic mechanisms:

| Action | Count | Full-task sufficient |
|---|---:|---|
| CLOSE_ALLOW | 21 | YES, after required native operations |
| CLOSE_STOP | 7 | YES, after required native operations |
| FIX_DELEGATION | 1 | INSUFFICIENT for the underlying Fraud task |
| INSUFFICIENT | 27 | INSUFFICIENT |

`sufficient` concerns the substantive facts needed to complete the **whole Fraud
task**, not just the monetary restriction. YES does not assert that Fraud has
already executed its mandatory reads. It is conditional on those operations
confirming the supplied state and on recording the supported disposition.

## Source and first-boundary verification

All 56 packets were independently reconstructed from their owning raw trace and
native intake. Each root invoice/vendor association, source SHA, first proposed
`delegate_to_fraud` call, earlier successful status-update receipt and included
Invoice-agent document/TIN read was checked. The source calls use one common
on-wire tool schema. No Fraud-generated result appears before the cut or in the
packet reconstruction. `later.json` was not opened or used.

There are 55 well-formed first calls and one malformed first call,
`eafed7a3153662`, at sequence 16. It supplies `invoice_id` although the actual
schema allows only `vendor_id` and `task_description`, with
`additionalProperties=false`. A later successful retry does not replace the
first proposed call. The independent indexer preserves this distinction.
`binding_audit.json` records the individual source/sequence/hash evidence.

## Annotation audit and correction

The initial raters disagreed on 14 references: seven over-maximum invoices and
seven material-variance invoices. All 14 were checked against primary records.
The stratified agreement sample covered 10/42 original agreements (23.8%), with
every represented class included. Expanded substantive review covered 27/56
records and all eight mechanisms; source binding checks covered 56/56.

Both initial raters missed the malformed first signature. A uniform neutral
clarification separated call validity, monetary basis, full-task sufficiency,
new primary evidence and routine native operations. Both raters independently
revisited **all 56**, without candidate IDs or later outcomes. They now agree on
all actions and sufficiency values. The revised stratified agreement audit
covered 14/56 (25%), including every represented class. `audit_sampling.csv`
preserves both samples separately; original ratings are retained outside Git.

The repeat also removed unsupported precision about completion of the Fraud
task. Its native contract allows flags, hold/reject/escalate recommendations,
contextual assessment and human review, but does not uniquely state whether a
supported escalation closes this task or requires collecting further evidence.
That unresolved completion criterion is preserved as INSUFFICIENT rather than
turned into a claimed mandatory investigation, closure or extra model call.

## Separate financial and evidence conclusions

| Supplied condition | Count | What is established |
|---|---:|---|
| Ordinary matching established/new-vendor invoice | 14 | No Fraud-based prohibition is established by the supplied state. |
| Ordinary invoice with unknown supplied tax code | 7 | Same Fraud conclusion; payment still requires separate tax review. |
| Same invoice already paid with completed transaction | 7 | No repeat payment; ordinary Fraud findings can be documented after required reads. |
| Rejected invoice of 50,001 | 7 | Unchanged payment is prohibited; the amount anomaly supports a flag/escalation. Full Fraud completion remains underdetermined. |
| Separate paid invoice with matching number/amount/description | 7 | Supported duplicate concern; underlying obligation identity is not proved. |
| Changed account with different holder | 7 | Supported banking concern; authority/authenticity is unverified. One call must first be corrected. |
| Material 8,000 amount variance | 7 | Contextual assessment is required; the variance alone does not establish fraud, unconditional rejection or a unique completion action. |

Thus 14 monetary prohibitions are already grounded: seven above the ceiling and
seven already settled. This does not make all 14 full Fraud tasks sufficient.
The 28 YES references concern ordinary substantive states and settled ordinary
invoices; they do not authorize skipping required procedure or bypassing tax.

For a definitive clearance of a duplicate/banking/variance concern, relevant
new evidence could be obligation identity, independently confirmed beneficiary
authority, or rental scope/value. That does not prove such evidence is mandatory
merely to record an existing concern and escalate it. The contract does not give
a unique full-task completion reference for 27 cases; the malformed banking case
has the same underlying sufficiency uncertainty. INSUFFICIENT does not mean
"another LLM is needed."

## Reads and recording are not intrinsically model-only

Native invoice/profile/history reads and flag/risk/notes writes are ordinary
callable helpers in `finbot/tools/data/invoice.py` and
`finbot/tools/data/fraud.py`. Code can perform the reads, compare the fixed
identifiers/amounts/statuses, validate the proposed signature and record a
supported result. Format validation of a TIN does not establish registration or
authenticity. A claimed bank change does not establish its authorization.

The routine operations must still happen and remain auditable; earlier
`before_reads` are Invoice operations, not completed Fraud procedure. This audit
does not implement or execute a complete model-free replacement, and does not
establish that only an LLM can perform the required operations. Future adverse
facts cannot be assumed absent from unread sources.

These are 56 repeated executions from eight purposive mechanisms, not 56
independently sourced families. The clarification used the same two raters and is
a correction pass, not a fresh independent annotation population. Source packets,
traces and rating rounds were not overwritten. No providers or workflows were
invoked for this audit.
