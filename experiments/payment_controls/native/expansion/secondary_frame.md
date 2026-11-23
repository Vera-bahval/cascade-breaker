# New Britain supplier-pair frame

The City of New Britain, Connecticut publishes the **Payable Transactions by Vendor** reports in Common Council packets. Seven official packets supplied 9,793 distinct extractable records across 623 register pages. Twelve incomplete rows were omitted. The register identifies the city vendor, invoice number and date, check number and date, payment status and invoice-linked amount. The source is a record of payment and does not adjudicate authorization, fraud, or the later invoice's status at an intervention point. [City archive](https://www.newbritainct.gov/gov/common-council/agenda-minutes-live-stream-n-videohtm)

A pair requires two paid records for the same city vendor ID under the same normalized organization name, distinct invoice numbers and check numbers, positive amounts up to 10,000 USD on both records, and payment of the earlier invoice strictly before the later invoice date. Rows that repeat the normalized invoice number within the observed supplier group were excluded, including repeated records on the same report. Exact repeated records across different packets were deduplicated. Multiple invoices can be itemized on the same check in this register. Each selected invoice has one distinct observed row and the pair uses two distinct checks. This supports the observed invoice-linked paid amount to the cent within these reports. The files do not establish an invoice's face value or exclude payments or adjustments outside the observed packets.

A legal-name suffix was required for organizational suppliers. The local cross-source check normalized punctuation, spacing and terminal legal designators and removed all matches against the 687 normalized name keys in the captured DC page. Eighty-five available New Britain records matched those keys after payment and organization filtering. Name matching across both sources remains bounded to their captured records and spellings. These reports do not establish ownership or an alias register.

The frozen frame contains **244 distinct organizational supplier pairs**, 73 above the requested additional 171. Two hundred thirty-two pairs have a purchase order number on both records. Seventy-six pairs have identical paid amounts. Within a supplier, selection favored purchase-order evidence on both records, then closer amounts, then shorter positive chronology. Selection used only the source fields and preceded FinBot outcomes. PDFium independently matched the issue date, check number and date, paid status and exact cents for all 488 enrolled records. [Source documents, SHA-256 hashes and counts](secondary_frame_manifest.json)

| Register packet | Selected later invoices |
|---|---:|
| December 2024 | 1 |
| March 2025 | 13 |
| April 2025 | 25 |
| May 2025 | 53 |
| September 2025 | 17 |
| October 2025 | 52 |
| November 2025 | 83 |

The extractor assigned an HMAC to each supplier, invoice and selected payment reference using a local key. The private frame retains exact amounts in integer cents and dates needed to preserve intervals. The source PDFs, DC name lookup, frame, evidence coordinates and key stay under ignored runtime paths. Names, original identifiers and free text do not enter the frame. Native FinBot reuses the existing local simulation and date translation with the NB- source blocks. The extraction made no model calls.

To reproduce, keep the captured PDFs with the names given in the manifest. Copy the original key to a separate private output directory. Use pypdf version 7.1.1 and run:

```sh
python experiments/payment_controls/native/expansion/secondary_frame.py \
  .runtime/secondary-frame .runtime/public_frame/source-response.json .runtime/secondary-frame-replay
```

Run the independent extraction check with pypdf and pypdfium2 installed:

```sh
python experiments/payment_controls/native/expansion/secondary_frame_audit.py \
  .runtime/secondary-frame .runtime/public_frame/source-response.json
```
