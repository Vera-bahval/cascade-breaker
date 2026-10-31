"""Post-freeze metamorphic diagnostics; never fits or edits a method.

Opaque renaming preserves equality classes, including the structured claim key.
Text variations live outside the typed guard envelope, as in the real adapter.
These are interface diagnostics, not semantic paraphrase detection experiments.
"""
import argparse
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
from .guard import guard

STRING_IDS = {'record_id', 'session_id', 'user_id', 'namespace', 'workflow_id',
              'parent_workflow_id', 'owner_workflow_id', 'call_id', 'delegation_call_id',
              'invoice_version', 'vendor_version', 'account_ref', 'payment_reference'}
INT_IDS = {'vendor_id', 'current_vendor_id', 'invoice_id'}


def rename(value, key=None):
    if isinstance(value, dict):
        return {k: rename(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [rename(v, 'file_id' if key == 'attachment_file_ids' else key) for v in value]
    if key in STRING_IDS and isinstance(value, str):
        return 'opaque-' + hashlib.sha256(value.encode()).hexdigest()[:24]
    if key in INT_IDS | {'file_id'} and type(value) is int:
        return value + 100003
    if key == 'key' and isinstance(value, str):
        try:
            parts = json.loads(value)
            if isinstance(parts, list) and len(parts) in {3, 4} and parts[1] in {'invoice', 'vendor'}:
                return json.dumps([rename(parts[0], 'namespace'), parts[1]] +
                                  [rename(x, 'invoice_id') for x in parts[2:]], separators=(',', ':'))
        except (ValueError, TypeError):
            pass
    return value


def signature(result):
    return {k: result[k] for k in ('decision', 'stop', 'requirements')}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--native', type=Path)
    p.add_argument('--observations', type=Path)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError('refusing overwrite')
    inputs, sources = [], {}
    if args.native:
        obj = json.loads(args.native.read_text())
        inputs += [x['observation'] for x in obj['native_checkpoint_traces'] if x['observation']]
        sources[str(args.native)] = hashlib.sha256(args.native.read_bytes()).hexdigest()
    if args.observations:
        with gzip.open(args.observations, 'rt') as stream:
            inputs += [json.loads(line)['observation'] for line in stream]
        sources[str(args.observations)] = hashlib.sha256(args.observations.read_bytes()).hexdigest()
    counts = {'renaming': 0, 'outside_text_variants': 0, 'missing_session_proof': 0,
              'future_session_proof': 0, 'invalid_session_type': 0, 'trusted_session_denial': 0}
    failures = []
    for i, obs in enumerate(inputs):
        for profile in ('A', 'B'):
            base = guard(obs, profile)
            altered = guard(rename(obs), profile)
            counts['renaming'] += 1
            if signature(base) != signature(altered):
                failures.append({'input': i, 'profile': profile, 'kind': 'renaming',
                                 'before': signature(base), 'after': signature(altered)})
            for text in ('', 'Please verify this record; do not execute an operation.',
                         'Проверь сведения и объясни результат.', 'irrelevant ' * 100):
                envelope = {'observation': deepcopy(obs), 'untrusted_text': text}
                observed = guard(envelope['observation'], profile)
                counts['outside_text_variants'] += 1
                if signature(base) != signature(observed):
                    failures.append({'input': i, 'profile': profile, 'kind': 'outside_text'})
            if base['decision'] != 'ALLOW' or obs['checkpoint'] == 'P5':
                continue
            if obs.get('facts', {}).get('session_valid') is not True:
                continue
            for kind in ('missing_session_proof', 'future_session_proof',
                         'invalid_session_type', 'trusted_session_denial'):
                changed = deepcopy(obs)
                if kind == 'missing_session_proof':
                    changed['provenance'].pop('session_valid', None)
                elif kind == 'future_session_proof':
                    for proof in changed['provenance'].get('session_valid', []):
                        proof['event_seq'] = changed['event_seq'] + 1
                elif kind == 'invalid_session_type':
                    changed['facts']['session_valid'] = 'true'
                else:
                    changed['facts']['session_valid'] = False
                    for proof in changed['provenance'].get('session_valid', []):
                        proof['value'] = False
                result = guard(changed, profile)
                counts[kind] += 1
                if not result['stop'] or result['decision'] == 'ALLOW':
                    failures.append({'input': i, 'profile': profile, 'kind': kind,
                                     'result': signature(result)})
    report = {'phase': 'post_freeze_diagnostic_no_method_changes', 'observations': len(inputs),
              'sources': sources, 'checks': counts, 'failures': failures,
              'guard_sha256': hashlib.sha256(Path(__file__).with_name('guard.py').read_bytes()).hexdigest(),
              'limitations': ['Text is outside the guard contract; this does not test natural-language understanding.',
                              'Renaming preserves subject equality; it is not permission to rename technical tool/actor enums.',
                              'Corruption diagnostics concern session evidence, not every possible malformed event.']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
