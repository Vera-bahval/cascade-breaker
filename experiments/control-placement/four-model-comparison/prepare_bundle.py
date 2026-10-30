"""Package existing evidence for publication. Never imports an inference runner."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
CONTROL = HERE.parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def public_value(value):
    if isinstance(value, list):
        return [public_value(v) for v in value]
    if not isinstance(value, dict):
        return value
    result = {k: public_value(v) for k, v in value.items()}
    # Служебные сведения внешнего аккаунта не участвуют в расчёте эксперимента.
    if 'response' in result and ('stats' in result or 'cost' in result):
        result.pop('key', None)
    if isinstance(result.get('stats'), dict) and any(k in result['stats'] for k in ('user', 'quota', 'usage')):
        result['stats'] = {k: v for k, v in result['stats'].items() if k in ('provider', 'model_family')}
    if isinstance(result.get('eliza_stats'), dict):
        result['eliza_stats'] = {k: v for k, v in result['eliza_stats'].items() if k in ('provider', 'model_family')}
    if isinstance(result.get('raw_body'), str):
        try:
            original = json.loads(result['raw_body'])
        except ValueError:
            pass
        else:
            cleaned = public_value(original)
            if cleaned != original:
                result['raw_body_original_sha256'] = sha(result['raw_body'].encode())
                result['raw_body'] = json.dumps(cleaned, ensure_ascii=False, separators=(',', ':'))
    return result


def publication_bytes(path):
    original = path.read_bytes()
    if path.name.endswith('.json.gz'):
        value = json.loads(gzip.decompress(original))
        cleaned = public_value(value)
        if cleaned != value:
            return gzip.compress(json.dumps(cleaned, ensure_ascii=False, separators=(',', ':')).encode(), mtime=0)
        return original
    compressed = path.name.endswith('.jsonl.gz')
    if compressed or path.suffix == '.jsonl':
        data = gzip.decompress(original) if compressed else original
        rows = [json.loads(line) for line in data.decode().splitlines() if line.strip()]
        cleaned = public_value(rows)
        if cleaned != rows:
            data = ''.join(json.dumps(v, ensure_ascii=False, separators=(',', ':'))+'\n' for v in cleaned).encode()
        # Исходный журнал содержит отдельный gzip-поток на каждую запись.
        # Единый контейнер сохраняет байты JSONL и существенно уменьшает архив.
        return gzip.compress(data, mtime=0) if compressed else data
    elif path.suffix == '.json':
        value = json.loads(original)
        cleaned = public_value(value)
        if cleaned != value:
            return (json.dumps(cleaned, ensure_ascii=False, indent=2)+'\n').encode()
    return original


def bundle(source, files, name, inventory):
    target = HERE/'artifacts'/name
    members = {}
    with target.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0, filename='') as gz:
        with tarfile.open(fileobj=gz, mode='w') as tf:
            for path in sorted(set(files)):
                relative = str(path.relative_to(source))
                original = path.read_bytes()
                data = publication_bytes(path)
                compressed_journal = path.name.endswith('.jsonl.gz')
                old_content = gzip.decompress(original) if compressed_journal else original
                new_content = gzip.decompress(data) if compressed_journal else data
                item = tarfile.TarInfo(relative)
                item.size = len(data); item.mode = 0o644; item.mtime = 0
                tf.addfile(item, io.BytesIO(data))
                members[relative] = {'source_sha256': sha(original), 'published_sha256': sha(data),
                                     'source_bytes': len(original), 'published_bytes': len(data),
                                     'source_content_sha256': sha(old_content), 'published_content_sha256': sha(new_content),
                                     'gzip_container_recompressed': compressed_journal and data != original,
                                     'public_metadata_filtered': new_content != old_content}
    if target.stat().st_size >= 95*2**20:
        raise ValueError('Split archive before GitHub publication: '+name)
    inventory[name] = {'sha256': sha(target.read_bytes()), 'bytes': target.stat().st_size, 'members': members}


def useful(path):
    return path.is_file() and not path.name.endswith(('.db', '.db-wal', '.db-shm', '.lock', '.pyc')) and '__pycache__' not in path.parts


def source_revision(source, ref):
    return subprocess.check_output(['git', '-C', str(source), 'rev-parse', ref], text=True).strip()


def prepare(source):
    source = source.resolve()
    (HERE/'artifacts').mkdir(exist_ok=True)
    inventory = {}
    inputs = {}
    for model, package, run in [('deepseek', 'deepseek_flash', 'paid'), ('luna', 'gpt_6_luna', 'subscription-resume-1')]:
        base = source/'experiments/control-placement'/package
        root = base/'results'/run
        defenders = {str(p.parent.relative_to(root/'main/episodes')): json.loads(p.read_text())
                     for p in root.glob('main/episodes/*/*/defender.json')}
        (HERE/'inputs'/f'{model}-defenders.json.gz').write_bytes(gzip.compress(
            json.dumps(defenders, ensure_ascii=False, separators=(',', ':')).encode(), mtime=0))
        for batch in range(1, 6):
            files = []
            for job in root.glob('main/episodes/*/*/job.json'):
                if json.loads(job.read_text())['batch'] == batch:
                    files.extend(p for p in job.parent.iterdir() if useful(p))
            bundle(source, files, f'{model}-main-batch-{batch}.tar.gz', inventory)
        phases = ['pilot', 'smoke', 'history', 'archived-openrouter-smoke'] if model == 'deepseek' else [
            'pilot-medium', 'pilot-high', 'smoke-medium', 'smoke-high', 'smoke', 'failed-main-1']
        files = [p for phase in phases for p in (root/phase).rglob('*') if useful(p)]
        if model == 'deepseek':
            files += list((root/'incidents').rglob('*.md'))
        bundle(source, files, f'{model}-additional-attempts.tar.gz', inventory)
        files = list(base.glob('*.py'))
        files += [p for directory in ('tests', 'verification') for p in (base/directory).glob('*.py')]
        files += [p for p in base.glob('*.md')]
        names = ['manifest.json', 'dependencies.json', 'budget.json', 'forecast.json', 'final-acceptance.json'] if model == 'deepseek' else [
            'manifest.json', 'recovery-policy.json', 'recovery-dry-accepted.json', 'prefix-copy-audit.json',
            'retry-wire-equality.json', 'retry-accepted.json', 'checkpoint-4.json', 'checkpoint-5.json',
            'main-forecast-latest.json', 'usage-final.json', 'cleanup.json', 'final-verification.json', 'export/receipt.json']
        files += [root/n for n in names if (root/n).is_file()]
        ledger = root/('checkpoints/batch-5/budget.sqlite.gz' if model == 'deepseek' else 'export/budget.snapshot.sqlite.gz')
        files.append(ledger)
        if model == 'deepseek':
            proof = json.loads((root/'final-quota-reconciliation.json').read_text())
            keep = {k: proof[k] for k in ('accepted', 'at', 'cost_usd', 'successful_paid_requests', 'unknown_requests')}
            keep['source_sha256'] = sha((root/'final-quota-reconciliation.json').read_bytes())
            (HERE/'inputs/deepseek-billing-proof.json').write_text(json.dumps(keep, indent=2)+'\n')
        bundle(source, files, f'{model}-source-and-acceptance.tar.gz', inventory)
    for path in (HERE/'inputs').iterdir():
        if path.is_file() and path.name.endswith(('.json', '.json.gz')):
            path.write_bytes(publication_bytes(path))
    for path in sorted((HERE/'inputs').iterdir()):
        if path.is_file():
            inputs[path.name] = {'published_sha256': sha(path.read_bytes()), 'bytes': path.stat().st_size}
    receipt = {'source_commit': source_revision(source, 'HEAD'),
               'anastasia_branch': 'research/control-placement', 'anastasia_commit': source_revision(source, 'origin/research/control-placement'),
               'base_main_commit': source_revision(source, 'origin/main'),
               'projection': 'Only Eliza envelope key, stats.user/stats.quota/stats.usage, and corresponding eliza_stats are removed from public copies; cost/native usage/model context kept. Original, published and decompressed-content hashes recorded separately. Raw HTTP JSON strings receive the same projection. Concatenated per-record gzip streams are recompressed into one gzip stream without changing logical JSONL bytes unless metadata was filtered.',
               'new_model_requests': 0, 'archives': inventory, 'inputs': inputs}
    (HERE/'artifacts/manifest.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    return {'archives': len(inventory), 'MiB': sum(v['bytes'] for v in inventory.values())/2**20,
            'filtered_files': sum(m['public_metadata_filtered'] for v in inventory.values() for m in v['members'].values())}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source)))
