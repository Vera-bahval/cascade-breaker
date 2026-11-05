# Contract serialization clarifications before blind predictions

Methods and observation contract were frozen on 2026-11-01T15:16:06Z. The following
serialization/applicability clarifications were supplied to the independent author
and reviewer from the frozen contract, without reading their cases or labels:

- Invoice claim key JSON: [namespace, "invoice", invoice_id, vendor_id]. Vendor-wide
  key: [namespace, "vendor", vendor_id]; same-owner vendor-wide admission covers invoices.
- Proof operation is a nonempty string; session_valid requires session_validate;
  server_context currency requires currency_contract_attest. Scope/delegation proofs
  bind current call_id. Actual parent tuple is additionally required for delegation.
- A09 applies only at P2/delegate_to_fraud and P3/update_invoice_status. At nonapproved
  invoice targets it is satisfied; at approved targets known HOLD/badamount/inactive
  vendor veto. A05 separately handles missing approval facts. Other tools N/A.
- Malformed enclosing JSON gets global UNKNOWN, independent of raw requirement-state
  placeholders. Canonical metadata routes a corrupted checkpoint/sequence but never
  repairs the body delivered to a guard.

No candidate code or thresholds changed in response. Test-specific findings are
kept between author/reviewer until prediction hashes are committed.
