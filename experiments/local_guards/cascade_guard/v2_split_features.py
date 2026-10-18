"""Blind collection views: validate/join identities without inspecting risk or labels."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def split(inputs, scores, destination):
    sources = {}
    collections = {}
    for collection, path in inputs.items():
        collections[collection] = set()
        for line in Path(path).open():
            row = json.loads(line)
            key = row['prefix_id']
            if key in sources:
                raise ValueError('Overlapping or duplicate collection prefix')
            sources[key] = (collection, row['input_hash'])
            collections[collection].add(key)
    score_hash = digest(scores)
    contents = {name: [] for name in inputs}
    seen = set()
    blocks = set()
    for line in Path(scores).open():
        row = json.loads(line)
        key = row['prefix_id']
        if key not in sources or key in seen:
            raise ValueError('Unexpected or duplicate score prefix')
        name, expected_hash = sources[key]
        if row['input_hash'] != expected_hash:
            raise ValueError('Input/score hash mismatch')
        seen.add(key)
        blocks.add(row['block'])
        contents[name].append(line if line.endswith('\n') else line + '\n')
    if seen != set(sources) or len(blocks) != 1:
        raise ValueError('Require one complete finished model stage')
    if score_hash != digest(scores):
        raise ValueError('Score stage changed during split')
    block = next(iter(blocks))
    outputs = {}
    for name, lines in contents.items():
        path = Path(destination)/name/(block+'.jsonl')
        text = ''.join(lines)
        if path.exists() and path.read_text() != text:
            raise ValueError('Preserve existing feature-view generation')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        outputs[name] = {'path': str(path), 'records': len(lines), 'sha256': digest(path)}
    manifest = {'role': 'blind collection-only identity/hash partition; no labels or risk selection',
        'block': block, 'source_sha256': digest(__file__), 'scores_sha256': score_hash,
        'input_sha256': {name: digest(path) for name, path in inputs.items()}, 'outputs': outputs}
    Path(destination).mkdir(parents=True, exist_ok=True)
    path = Path(destination)/(block+'-split-manifest.json')
    serialized = json.dumps(manifest, indent=2)+'\n'
    if path.exists() and path.read_text() != serialized:
        raise ValueError('Preserve existing split manifest')
    path.write_text(serialized)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs-directory', type=Path, required=True)
    parser.add_argument('--scores', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    names = {'archive':'archive-p4-inputs.jsonl', 'archive-partial':'archive-partial-inputs.jsonl',
        'raw64':'raw64-inputs.jsonl', 'raw64-partial':'raw64-partial-inputs.jsonl',
        'independent':'independent-p4-inputs.jsonl'}
    manifest = split({name: args.inputs_directory/file for name,file in names.items()}, args.scores, args.output)
    print(json.dumps({'block': manifest['block'], 'collections': {k:v['records'] for k,v in manifest['outputs'].items()}}))


if __name__ == '__main__':
    main()
