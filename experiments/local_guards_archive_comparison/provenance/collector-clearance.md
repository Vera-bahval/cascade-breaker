# Focused collector/common-view clearance

**PASS for the exact source and view hashes below.** C1/C2 from the original collector review and the subsequently discovered C3 status corruption are resolved. This supersedes that review's common-view changes-required verdict; other release gates remain separate.

- `views.py`: `34d2db3964406c0ecc96424f154721900bb46b0758d96bf10698c33a076dcdce`
- Historical views: `c077ca45ba288ee36546994c9b7d811b5973af88bb04e4c0755e58ed053c13ac`
- Instrumented views: `09f4bd3d898e32cee6bd219405952fb0d9328e08fe92728063b3f17f5bb3ca95`

The serialized-result/query bypass and vendor-name/email/run-slug leakage are repaired. An independent 10,820-row stream scan after those repairs found no remaining full legacy run slugs or original vendor identity strings, and no actual monetary/numeric scalar changes. It identified six residual invoice-name exposures in underscore-adjacent filenames: `Invoice_INV-2026-1134.pdf` and `INV-2026-1000_review.pdf`. The final boundary fix removes these in all three affected prefix IDs, checked in both modes. This avoids claiming an expensive full leak rescan was repeated after the final two amendments.

That scan also discovered C3: `evidence_status.invoice_number=observed` was incorrectly treated as an invoice identity, registering status words as aliases and changing source status strings throughout the view. The fix excludes the entire evidence-status map from identity scanning and copies it unchanged. Final focused actual-row readback confirms exact canonical status mappings, valid status enums and retained source-proof values.

The final 11 view tests pass independently, including serialized native containers, arbitrary queries, vendor identity, alias replacement, underscore filename linkage, unchanged evidence statuses, empty/malformed IDs and lossless duplicate-string packing. Six actual prefix IDs were checked in each mode: `59cff680a4a55fe690b1eae191db`, `6a070b0e75a37cb31019b3c65d2d`, `618d77787e19ed630c1c855488c8`, `5627dcd26dd3be24cd3c8bd23caa`, `130e92fc47bab734749b799dab89`, `d8847a554ab06f5c40939bd3058a`.

Source meaning is preserved: invoice amount 1820 versus proposal 1970.15 still disagrees while the account agrees; the legacy 800 versus 920 proposal still disagrees and retains a different recipient. Amount/account/invoice/recommendation proofs match their corresponding facts. Actual pack/unpack roundtrips previously passed on these representative views, and the final packing unit test remains green. Native numeric IDs are retained for joins and must remain excluded from ML features.

The collector now gates native state ingestion on a valid paired return, addressing the earlier bounded malformed-input risk. The pairing-correction receipt remains separate from view normalization. This review does not replace independent action labels, downstream method-feature checks, or the author's final all-row schema/pack validation receipt at `provenance/view-validation.json`.

No API, executor, source/label edit, target-method read, prediction or commit was used. Only this clearance and its JSON receipt were written in this follow-up.
