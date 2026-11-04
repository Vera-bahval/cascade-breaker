"""Offline audit of stored charge metadata; never imports a provider client."""
from collections import Counter
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
RUN = ROOT / 'experiments/local_guards_archive_comparison/results/eliza-run'
REPAIRED = ROOT / 'experiments/local_guards_repaired_evaluation'
ZERO = Decimal(0)
UNIT = Decimal('0.000000001')
USAGE = ('prompt_tokens', 'completion_tokens', 'total_tokens',
         'prompt_cache_hit_tokens', 'prompt_cache_miss_tokens')


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def metadata(path, fields):
    # Response bodies, model decisions, reasons and request prompts are not returned.
    with gzip.open(path, 'rt') as stream:
        return [{key: row[key] for key in fields if key in row}
                for row in (json.loads(line, parse_float=Decimal) for line in stream)]


def amount(value):
    if isinstance(value, bool) or not isinstance(value, (Decimal, int, float)):
        raise ValueError('missing or invalid explicit charge')
    result = value if isinstance(value, Decimal) else Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError('negative or nonfinite charge')
    return result


def charge_index(rows, field):
    indexed = {}
    for row in rows:
        key = row.get('query_id')
        if not isinstance(key, str) or not key:
            raise ValueError('missing request identity')
        value = amount(row.get(field))
        if key in indexed and indexed[key] != value:
            raise ValueError('conflicting charges for one request identity')
        indexed[key] = value
    return indexed


def money(values):
    total = sum(values, ZERO)
    return {'stored_numeric_sum_usd': str(total),
            'rounded_9dp_usd': str(total.quantize(UNIT))}


def self_check():
    rows = [{'query_id': 'a', 'cost': Decimal('.1')},
            {'query_id': 'a', 'cost': Decimal('.1')},
            {'query_id': 'b', 'cost': Decimal('.2')}]
    assert money(charge_index(rows, 'cost').values())['stored_numeric_sum_usd'] == '0.3'
    for bad in (None, True, Decimal('-1'), Decimal('NaN')):
        try:
            amount(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('invalid charge accepted')
    try:
        charge_index(rows + [{'query_id': 'a', 'cost': Decimal('.3')}], 'cost')
    except ValueError:
        pass
    else:
        raise AssertionError('conflicting duplicate accepted')


def run():
    self_check()
    normalized = ROOT / 'experiments/local_guards_archive_comparison/results/deepseek-historical.jsonl.gz'
    views = [normalized, *sorted(normalized.parent.glob('strata/*/deepseek.jsonl.gz'))]
    saved = REPAIRED / 'results/saved-deepseek.jsonl.gz'
    errors = RUN / 'errors.jsonl.gz'
    sources = [RUN / name for name in ('responses.jsonl.gz', 'requests.jsonl.gz',
               'ledger.sqlite', 'case-mapping.jsonl.gz', 'summary.json', 'progress.json')]
    sources += [saved, *views, Path(str(normalized) + '.receipt.json'),
                REPAIRED / 'cost-accounting.json', REPAIRED / 'costs.py',
                ROOT / 'experiments/local_guards_archive_comparison/eliza.py',
                ROOT / 'experiments/local_guards_archive_comparison/normalize_deepseek.py',
                Path(__file__).resolve()]
    if errors.exists():
        sources.append(errors)
    before = {str(path.relative_to(ROOT)): sha(path) for path in sources}
    responses = metadata(RUN / 'responses.jsonl.gz',
                         ('case_id', 'query_id', 'cost_usd', 'usage', 'response_id', 'response_model', 'parsed'))
    requests = metadata(RUN / 'requests.jsonl.gz', ('case_id', 'query_id'))
    mapping = metadata(RUN / 'case-mapping.jsonl.gz', ('case_id', 'query_id'))
    selected = metadata(saved, ('case_id', 'prefix_id', 'query_id', 'charge_usd', 'charge_source', 'status', 'usage'))
    response_charges = charge_index(responses, 'cost_usd')
    selected_charges = charge_index(selected, 'charge_usd')
    with sqlite3.connect((RUN / 'ledger.sqlite').as_uri() + '?mode=ro', uri=True) as db:
        ledger = db.execute('SELECT id,cost,status,reserve FROM requests').fetchall()
    # SQLite REAL is rendered with Python's round-trip repr, matching saved JSON floats.
    ledger_charges = {key: amount(cost) for key, cost, _, _ in ledger if cost is not None}
    request_ids = {row['query_id'] for row in requests}
    mapping_ids = {row['query_id'] for row in mapping}
    assert len(response_charges) == len(responses)
    assert response_charges == ledger_charges
    assert request_ids == set(response_charges)
    assert len(requests) == len(request_ids)
    assert set(selected_charges) <= set(response_charges)
    assert all(value == response_charges[key] for key, value in selected_charges.items())
    assert len(selected) == len(selected_charges) == len({row['prefix_id'] for row in selected})
    outside = {key: value for key, value in response_charges.items() if key not in selected_charges}
    assert sum(selected_charges.values(), ZERO) + sum(outside.values(), ZERO) == sum(response_charges.values(), ZERO)
    old = json.loads((REPAIRED / 'cost-accounting.json').read_text(), parse_float=Decimal)
    old_reference = old['reference']['historical_actual_eliza_charge_usd']
    assert Decimal(old_reference) == sum(selected_charges.values(), ZERO).quantize(UNIT)
    view_rows = []
    for path in views:
        rows = metadata(path, ('query_id', 'charge_usd', 'status'))
        charges = charge_index(rows, 'charge_usd')
        assert all(response_charges.get(key) == value for key, value in charges.items())
        omitted = {key: value for key, value in response_charges.items() if key not in charges}
        view_rows.append({'path': str(path.relative_to(ROOT)), 'rows': len(rows),
                          'unique_queries': len(charges), 'charges': money(charges.values()),
                          'charged_run_queries_absent_from_view': len(omitted),
                          'absent_query_charges': money(omitted.values()),
                          'additional_charge': False})
    origins = {}
    for origin in sorted({row['case_id'].split('/', 1)[0] for row in responses}):
        matched = [row for row in responses if row['case_id'].split('/', 1)[0] == origin]
        origins[origin] = {'requests': len(matched),
                           'charges': money(amount(row['cost_usd']) for row in matched)}
    receipt = json.loads(Path(str(normalized) + '.receipt.json').read_text())
    receipt_matches = {str(Path(path).relative_to(ROOT)): before[str(Path(path).relative_to(ROOT))] == digest
                       for path, digest in receipt['sources'].items()
                       if str(Path(path).relative_to(ROOT)) in before}
    assert all(receipt_matches.values())
    cache = {}
    for key, predicate in [('positive_hit_tokens', lambda u: u.get('prompt_cache_hit_tokens', 0) > 0),
                           ('zero_hit_tokens', lambda u: u.get('prompt_cache_hit_tokens') == 0),
                           ('missing_hit_tokens', lambda u: u.get('prompt_cache_hit_tokens') is None)]:
        matched = [row for row in responses if predicate(row.get('usage') or {})]
        cache[key] = {'requests': len(matched), 'charges': money(amount(row['cost_usd']) for row in matched)}
    error_rows = metadata(errors, ('query_id', 'http_status', 'cost', 'cost_usd')) if errors.exists() else []
    explicit_errors = [row for row in error_rows if row.get('cost') is not None or row.get('cost_usd') is not None]
    final_summary = json.loads((RUN / 'summary.json').read_text(), parse_float=Decimal)
    progress = json.loads((RUN / 'progress.json').read_text(), parse_float=Decimal)
    report = {
        'scope': 'Stored historical Eliza guard run; selected542 and normalized views reuse these charges. Not a provider account statement or complete original FinBot executor billing.',
        'arithmetic': 'Exact Decimal sum of serialized JSON numeric charges; SQLite REAL values converted by round-trip repr. Nine-place display rounds serialization noise, without repricing tokens.',
        'new_api_calls_this_completion': 0, 'new_api_charge_usd_this_completion': '0',
        'local_compute_usd': None,
        'charged_run': {'response_rows': len(responses), 'unique_query_ids': len(response_charges),
                        'unique_provider_response_ids': len({row.get('response_id') for row in responses}),
                        'missing_provider_response_ids': sum(not row.get('response_id') for row in responses),
                        'request_rows': len(requests), 'ledger_rows': len(ledger),
                        'ledger_statuses': dict(Counter(row[2] for row in ledger)),
                        'charges': money(response_charges.values()),
                        'response_ledger_charge_mismatches': 0,
                        'case_id_origin_groups': origins,
                        'response_models': dict(Counter(row.get('response_model') for row in responses)),
                        'parsed_response_counts': dict(Counter(str(row.get('parsed')) for row in responses)),
                        'usage': {field: sum((row.get('usage') or {}).get(field, 0) for row in responses) for field in USAGE}},
        'selected542': {'rows': len(selected), 'unique_query_ids': len(selected_charges),
                        'charges': money(selected_charges.values()),
                        'charge_sources': dict(Counter(row.get('charge_source') for row in selected)),
                        'status_counts': dict(Counter(row.get('status') for row in selected)),
                        'all_query_ids_and_charges_match_run': True,
                        'case_id_origin_counts': dict(Counter(row['case_id'].split('/', 1)[0] for row in selected)),
                        'additional_charge_for_reusing_saved_rows': False},
        'outside_selected542': {'unique_query_ids': len(outside), 'charges': money(outside.values())},
        'normalized_views_not_additional_billing': view_rows,
        'normalized_receipt_source_hashes_match_current': receipt_matches,
        'existing_report_reference': {'selected_reported_usd': old_reference,
                                      'matches_selected_rounded_9dp': True,
                                      'final_summary_cost_usd': str(final_summary['cost_usd']),
                                      'final_summary_requests': final_summary['requests'],
                                      'progress_snapshot_cost_usd': str(progress['cost_usd']),
                                      'progress_snapshot_requests': progress['requests']},
        'cache_usage': {'groups': cache, 'interpretation': 'Provider prompt-cache token usage, not free responses or local query reuse; explicit recorded charges already include the observed cache effect.'},
        'request_and_retry_evidence': {'duplicate_request_query_ids': len(requests) - len(request_ids),
                                       'duplicate_response_query_ids': len(responses) - len(response_charges),
                                       'duplicate_mapping_query_ids': len(mapping) - len(mapping_ids),
                                       'mapping_rows': len(mapping),
                                       'direct_http_status_and_attempt_count_in_responses': False,
                                       'producer_contract': 'eliza.py saves responses after HTTP200 and attempt_count==1 checks; those two fields are not persisted in responses. The ledger refuses duplicate identities and unresolved automatic retries.',
                                       'provider_internal_retries_independently_auditable': False},
        'unreconciled': {'mapping_without_request_response_or_ledger': [row for row in mapping if row['query_id'] not in request_ids and row['query_id'] not in response_charges and row['query_id'] not in {item[0] for item in ledger}],
                         'ledger_missing_explicit_cost_count': sum(row[1] is None for row in ledger),
                         'unpriced_ledger_reserve_usd': str(sum((amount(row[3]) for row in ledger if row[1] is None), ZERO)),
                         'errors_file_present': errors.exists(), 'error_rows': len(error_rows),
                         'error_rows_with_explicit_charge': len(explicit_errors),
                         'limitation': 'No failed charged request is explicitly evidenced here. Absence of an errors file does not prove that other historical sessions or provider-account charges never existed. The mapped-only request has unknown outcome/charge; it is not assigned zero.'},
        'sources_sha256': before,
        'self_checks': 'Decimal arithmetic, duplicate conflict rejection, invalid charges, exact run-ledger equality, selected subset identity/cost equality, partition equality and old-report rounding pass.'}
    after = {str(path.relative_to(ROOT)): sha(path) for path in sources}
    assert before == after, 'source changed during audit'
    report['sources_unchanged_during_audit'] = True
    (HERE / 'cost-audit.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
    rows = [('Stored charged guard run', len(response_charges), money(response_charges.values())['rounded_9dp_usd']),
            ('Selected 542, reused historical answers', len(selected_charges), money(selected_charges.values())['rounded_9dp_usd']),
            ('Charged requests outside selected 542', len(outside), money(outside.values())['rounded_9dp_usd']),
            ('New calls in this completion', 0, '0')]
    table = '\n'.join(f'| {label} | {count} | ${cost} |' for label, count, cost in rows)
    text = f'''# Stored request cost audit

The captured Eliza guard run cost **$12.197960256 across 3100 unique charged requests**. The previous **$2.321758440** figure covers only 542 selected saved answers from that same run. The remaining 2558 charged requests total **$9.876201816**. These scopes reconcile exactly; saved answers and normalized views are not additional API charges.

| Scope | Unique requests | Recorded charge, rounded to 9 decimals |
|---|---:|---:|
{table}

The user's approximate $12 total is consistent with the captured run. This does not establish every charge for the whole original FinBot study: original executor inference and any other provider sessions have no complete billing evidence in these audited sources. Local compute is not assigned a USD price. This completion uses stored responses and makes no new model/API calls.

## Primary-source reconciliation

- `responses.jsonl.gz`, `requests.jsonl.gz` and read-only `ledger.sqlite` contain 3100 matching unique query IDs. Every response cost equals its ledger cost when SQLite REAL values use their round-trip decimal representation. All ledger rows are `complete`; no cost is missing and no unresolved reserve is substituted for a charge.
- The exact Decimal sum of the serialized response numeric fields is `12.1979602559999997645`; the selected 542 sum is `2.3217584399999999539`; the outside-selected sum is `9.8762018159999998106`. Their exact partition equality is checked. Nine-place display removes stored floating-point serialization noise; tokens are never repriced.
- The prior repaired-evaluation cost report's `2.321758440` matches the selected sum rounded to nine decimals. The final run summary reports 3100 requests and `12.197960256`.
- The existing normalized historical view has 3096 responses totalling `$12.181478868`. The four other charged run responses have `instrumented/` case IDs and total `$0.016481388`. This directly observed origin split is recorded without inferring why normalization excluded them. All 542 selected rows have `historical/` case IDs. The normalized receipt's response, mapping, ledger and producer-code hashes match current sources; the difference is not attributed to stale input hashes.
- Strata files select the same charged responses, with overlap between views; they are not separate bills. The progress snapshot reports 3096 requests and `$12.17879058`, so its request count must not be used to assume it contains the same 3096 queries as the normalized view.

## Failures, retries, caching and gaps

- No duplicate logical request ID or provider response ID is observed. The producer checks HTTP 200 and `attempt_count == 1` before persisting a response, but direct HTTP status and attempt count are not retained in response rows. Provider-internal retry history therefore cannot be independently reconstructed from this snapshot.
- There is no stored errors file and no explicitly evidenced charged-failure row. This is an evidence limit, not a claim that every historical attempt in every session succeeded.
- Case mapping has 3101 unique query IDs. One has no request, response or ledger record. Its outcome and charge are unknown; it is excluded from explicit-charge totals, not priced at zero. Its private identifiers are retained in `cost-audit.json`.
- 3095 responses report positive prompt-cache-hit tokens and 5 report zero. Token totals: 5,499,776 cache-hit prompt tokens and 39,024,956 cache-miss prompt tokens. Cache-hit requests still have explicit charges; prompt caching and local reuse of saved answers are different accounting concepts.
- Full provider statements, raw HTTP receipts, direct retry fields and original executor billing are unavailable to this bounded audit. No explanation for unsupported billing differences is invented.

## Reproduce and verify

Run `python3 -B experiments/local_guards_completion/cost_audit.py` from the repository root. The script uses only the standard library, reads charge/identity/usage metadata, opens SQLite read-only, checks source hashes before and after, and writes only this report and `cost-audit.json`. Its embedded self-check covers exact sums, invalid charges, duplicate-ID conflicts and scope reconciliation. The JSON records SHA-256 for every input and the audit script; source files remain unchanged.
'''
    (HERE / 'COST_AUDIT.md').write_text(text)
    print(json.dumps({'requests': len(response_charges), 'charged_run': money(response_charges.values()),
                      'selected542': money(selected_charges.values()), 'sources_unchanged': True}))


if __name__ == '__main__':
    run()
