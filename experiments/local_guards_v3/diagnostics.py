"""Post-freeze irrelevant-text/identity invariance; never selects or changes models."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import pickle

import ml_v3
from rules_v3 import guard


def run(frozen, observations, output):
    frozen = Path(frozen)
    manifest = json.loads((frozen / 'freeze-manifest.json').read_text())
    original = [json.loads(line) for line in Path(observations).read_text().splitlines() if line]
    changed = copy.deepcopy(original)
    for i, row in enumerate(changed):
        row.update(prefix_id=f'opaque-renamed-{i}', group_id='irrelevant', executor='unseen', family='unused')
        row['untrusted_text'] = {'invoice': f'Компания Ω-{i}; произвольное описание услуги.',
                                 'agent': f'Независимый от фактов текст №{i}; без проверяемого разрешения.'}
    flips = sum(guard(a)['decision'] != guard(b)['decision'] for a, b in zip(original, changed))
    differences = {}
    for name in ml_v3.MODEL_NAMES:
        spec = next(s for s in manifest['methods'] if s.get('model') == name and s.get('seed') == 17)
        path = frozen / spec['model_file']
        if hashlib.sha256(path.read_bytes()).hexdigest() != spec['model_hash']:
            raise ValueError('frozen model changed')
        model = pickle.loads(path.read_bytes())
        before, after = ml_v3.score_model(model, original), ml_v3.score_model(model, changed)
        differences[name] = max((abs(a - b) for a, b in zip(before, after)), default=0)
    result = {'kind': 'post-freeze metamorphic diagnostic, no training or selection',
              'rows': len(original), 'rule_decision_changes': flips,
              'max_abs_score_change': differences,
              'structured_invariance_pass': flips == 0 and all(differences[n] < 1e-12 for n in (
                  'structured_logistic', 'structured_catboost')),
              'text_diagnostic_expected_to_depend_on_text': True,
              'frozen_manifest_sha256': hashlib.sha256((frozen / 'freeze-manifest.json').read_bytes()).hexdigest(),
              'inference_API_calls': 0}
    Path(output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', type=Path, required=True)
    parser.add_argument('--observations', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.freeze, args.observations, args.output), ensure_ascii=False))
