# Public invoice-linked payment frame

The source is the District of Columbia government's [PASS Payments register](https://maps2.staging.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Government_Operations/MapServer/17). The portal describes each record as payment information. The district's [payment lookup](https://vendorportal.dc.gov/DCPayments) explains that a payment can cover multiple vouchers and purchase orders.

The local freeze uses the first successfully captured page ordered by `OBJECTID` for FY 2025 invoices dated June 2025. The query reported 2,071 eligible source rows before local filtering and returned 2,000 rows on the preserved page, with 1,999 distinct source object IDs. The DC service subsequently denied requests from the available network. No complete-register comparison is available for this freeze. Source filters require a purchase order, a usable invoice identifier, a payment and voucher reference, a chronologically consistent invoice and payment date, and an amount in (0, USD 10,000]. A supplier-name heuristic retains likely organizations based on legal-name tokens and excludes obvious non-supplier categories. Known legal suffixes, punctuation, and case are normalized before allocating one pair or single anchor to a supplier group. The register has no verified cross-reference for alternate supplier names or related legal entities.

The frozen page yielded 216 normalized supplier groups, of which 45 have an earlier distinct same-supplier invoice whose payment date precedes the later invoice date. The remaining 171 are single anchors. Four of the 45 selected pairs have identical source payment amounts. The two invoice records retain actual source amount and date locally. For this freeze the invoice, voucher and payment identifier uniqueness checks apply within the captured page. The earlier record is selected by smallest absolute amount difference, then latest payment date, then source row ID. A split or credit with a different identifier can also remain invisible. The resulting amount is the register's invoice-linked payment amount. The register provides no underlying legal approval, fraud adjudication, balance due, invoice face amount, or point-in-time pending state.

Enrollment prioritizes candidates with an observed sibling, then applies a fixed hash ordering of supplier, invoice and voucher keys. Experiment labels, model replies, and test outcomes are unavailable to the sampler. Materializing hypothetical later invoice states and prior-paid context inside FinBot is a simulation using observed source amounts and chronological spacing.

Rebuild the retained freeze into a separate private folder from the publication checkout with Python 3:

```sh
mkdir -m 700 .runtime/public_frame_replay
install -m 600 .runtime/public_frame/key .runtime/public_frame_replay/key
python3 experiments/payment_controls/native/expansion/public_frame.py \
  .runtime/public_frame_replay --snapshot .runtime/public_frame/source-response.json
```

The output directory and original source response are private. The response is kept as an audit witness under the ignored runtime directory and must be excluded from publication and vendor traffic. Invoices and evidence use keyed pseudonyms and omit supplier names, source invoice and payment identifiers, voucher and PO numbers, and source free text. They keep exact date and amount as local research data. The key stays in the private folder. External model inputs must omit these source-exact fields and keyed references. The manifest records the query scope and SHA-256 hashes of received responses and frozen artifacts. The API is a current mutable copy, so relaunching the extractor later can produce different candidate counts. Keep the original private frame and its manifest to replay the frozen cohort.
