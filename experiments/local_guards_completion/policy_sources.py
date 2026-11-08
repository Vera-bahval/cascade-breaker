"""Reproduce captured historical system instructions from verified episode archives.

Only same-episode .calls.jsonl input/system messages are projected. Model outputs,
tool definitions, usage, billing and authentication fields are not inspected.
"""
import argparse
from collections import defaultdict
import gzip
import hashlib
import json
from pathlib import Path
import tarfile

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
ARCHIVE_ROOT = HERE.parents[2] / 'finbot-four-model-report'
SCOPE = ('First system instruction per agent in same episode; full model outputs are excluded. '
         'Missing cases use explicitly declared historical native defaults, not current code.')
ACTORS = {'payments': 'autonomous payment processing assistant',
          'fraud': 'autonomous fraud and compliance',
          'invoice': 'invoice processing assistant'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def read_json(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt') as stream:
        return json.load(stream)


def read_rows(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt') as stream:
        return [json.loads(line) for line in stream if line.strip()]


def first_instructions(data):
    """Return exact first input/system text per recognized native actor."""
    found = {}
    for line_number, line in enumerate(data.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except (ValueError, UnicodeDecodeError) as error:
            raise ValueError(f'malformed calls JSON at line {line_number}') from error
        if not isinstance(row, dict) or not isinstance(row.get('input'), list):
            continue
        for message in row['input']:
            if not isinstance(message, dict) or message.get('role') != 'system' or not isinstance(message.get('content'), str):
                continue
            text = message['content']
            for actor, marker in ACTORS.items():
                if actor not in found and marker in text.lower():
                    found[actor] = dict(text=text, sha256=sha_bytes(text.encode()), source_line=line_number)
    return found


def extract(manifest, metadata, archive_root=ARCHIVE_ROOT):
    cases = read_json(manifest)['cases']
    ids = {r['prefix_id'] for r in cases}
    if len(ids) != len(cases):
        raise ValueError('duplicate selected prefix')
    selected = [r for r in read_rows(metadata) if r['prefix_id'] in ids]
    if len(selected) != len(ids) or {r['prefix_id'] for r in selected} != ids:
        raise ValueError('missing or duplicate selected metadata')
    archives = defaultdict(list)
    for row in selected:
        source = row['source']
        if source.endswith('.tar.gz'):
            path = Path(source)
            archives[path if path.is_absolute() else Path(archive_root) / path].append(row)
    policies, captured, verified = {}, {}, {}
    missing_members, unsupported_members = [], []
    for path, rows in sorted(archives.items()):
        expected = {r.get('source_sha256') for r in rows}
        if len(expected) != 1 or not isinstance(next(iter(expected)), str):
            raise ValueError(f'conflicting or absent archive hash: {path.name}')
        wanted = defaultdict(list)
        for row in rows:
            member = row.get('member')
            if not isinstance(member, str) or not member.endswith('.hooks.jsonl'):
                unsupported_members.append(row['prefix_id'])
                continue
            wanted[member[:-len('.hooks.jsonl')] + '.calls.jsonl'].append(row['prefix_id'])
        # Verify the entire archive before trusting any projected instruction.
        with path.open('rb') as stream:
            before = path.stat()
            h = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                h.update(chunk)
            actual = h.hexdigest()
            if actual != next(iter(expected)):
                raise ValueError(f'archive SHA-256 mismatch: {path.name}')
            verified[str(path.resolve())] = actual
            stream.seek(0)
            seen = set()
            with tarfile.open(fileobj=stream, mode='r|gz') as archive:
                for member in archive:
                    if member.name not in wanted:
                        continue
                    if member.name in seen or not member.isfile():
                        raise ValueError(f'ambiguous or non-file calls member: {member.name}')
                    seen.add(member.name)
                    data = archive.extractfile(member).read()
                    member_hash = sha_bytes(data)
                    instructions = first_instructions(data)
                    for prefix in wanted[member.name]:
                        if instructions:
                            captured[prefix] = {}
                        for actor, instruction in instructions.items():
                            key = instruction['sha256']
                            policy = dict(actor=actor, text=instruction['text'], sha256=key)
                            if key in policies and policies[key] != policy:
                                raise ValueError('inconsistent policy identity')
                            policies[key] = policy
                            captured[prefix][actor] = dict(policy_sha256=key, source_member=member.name,
                                source_line=instruction['source_line'], member_sha256=member_hash)
            after = path.stat()
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError(f'archive changed during extraction: {path.name}')
        missing_members.extend(prefix for name in set(wanted) - seen for prefix in wanted[name])
    index = dict(policies=policies, cases=captured, scope=SCOPE)
    audit = dict(selected_cases=len(ids), captured_cases=len(captured), unique_prompts=len(policies),
                 captured_actor_bindings=sum(len(v) for v in captured.values()),
                 verified_archive_sha256=verified, missing_calls_members=sorted(missing_members),
                 unsupported_hooks_members=sorted(unsupported_members),
                 interpretation='First actor invocation in the same episode; this is not a captured callable-list proof or proof that later invocations have identical policy. No post-P4 facts are projected.')
    return index, audit


def publish(path, value):
    """Canonical UTF-8 and gzip mtime=0; existing different files are preserved."""
    path = Path(path)
    if not str(path).endswith('.json.gz'):
        raise ValueError('published policy index must end in .json.gz')
    data = gzip.compress((canonical(value) + '\n').encode(), mtime=0)
    if path.exists():
        if path.read_bytes() != data:
            raise FileExistsError(path)
        return
    with path.open('xb') as stream:
        stream.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=EXP / 'local_guards_archive_annotation/custodian_manifest.json')
    parser.add_argument('--metadata', type=Path, default=EXP / 'local_guards_archive_comparison/data/metadata.jsonl.gz')
    parser.add_argument('--archive-root', type=Path, default=ARCHIVE_ROOT)
    parser.add_argument('--check', nargs='?', type=Path, const=HERE / 'captured-policies.json')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.check is None and args.output is None:
        parser.error('supply --check and/or --output')
    value, audit = extract(args.manifest, args.metadata, args.archive_root)
    if args.check is not None and read_json(args.check) != value:
        raise ValueError('captured policy index differs from freshly verified extraction')
    if args.output is not None:
        publish(args.output, value)
    print(canonical(dict(status='PASS', decoded_index_sha256=sha_bytes(canonical(value).encode()), **audit)))


if __name__ == '__main__':
    main()
