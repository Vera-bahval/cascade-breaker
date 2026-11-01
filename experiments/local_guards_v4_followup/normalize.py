"""Label-free structural normalization; equality is not semantic novelty evidence."""
import json

normalization_version = 'finbot-structural-v2'
IDENTITY = frozenset('record_id session_id user_id namespace workflow_id parent_workflow_id '
    'delegated_workflow_id owner_workflow_id call_id delegation_call_id source_call_id snapshot_id '
    'account_ref payment_reference vendor_id current_vendor_id invoice_id attachment_file_ids '
    'invoice_version vendor_version'.split())
JOIN_METADATA = frozenset('prefix_id original_prefix_id episode_id group_id pair_key pair_member family '
    'executor repeat split dataset scenario_id source_intent source_requires_stop source source_archive '
    'source_member source_version member cohort exposure metadata assumptions payment_baseline '
    'original_provenance'.split())
SEQUENCES = frozenset(('event_seq', 'approved_seq', 'acquired_seq'))


def normalize(observation):
    """Return canonical JSON, retaining null/absence, invalid shapes and ID equality.

    Strip metadata at the observation root only: proof.source is evidence, not a
    file provenance tag. ID types and invalid ID values remain distinguishable.
    Event ranks preserve relative order/equality; array order is never sorted.
    """
    if isinstance(observation, dict) and 'observation' in observation:
        observation = observation['observation']
    if isinstance(observation, dict):
        observation = {k: v for k, v in observation.items() if k not in JOIN_METADATA}
    times, symbols = set(), {}

    def scan(value, key=None):
        if key in SEQUENCES and type(value) is int and value >= 0:
            times.add(value)
        elif isinstance(value, dict):
            for k, v in value.items():
                scan(v, k)
        elif isinstance(value, list):
            for v in value:
                scan(v, key)
    scan(observation)
    ranks = {value: i for i, value in enumerate(sorted(times))}

    def identity(value):
        if value is None or value == '' or (isinstance(value, str) and not value.strip()):
            return value
        if type(value) not in (str, int) or (type(value) is int and value <= 0):
            return ['invalid-id', walk(value)]
        token = (type(value).__name__, value)
        if token not in symbols:
            symbols[token] = len(symbols) + 1
        return ['id', token[0], symbols[token]]

    def walk(value, key=None):
        if key in IDENTITY:
            if key == 'attachment_file_ids' and isinstance(value, list):
                return [identity(v) for v in value]
            return identity(value)
        if key == 'key' and isinstance(value, str):
            try:
                parts = json.loads(value)
            except ValueError:
                parts = None
            if isinstance(parts, list) and len(parts) in (3, 4) and parts[1] in ('invoice', 'vendor'):
                return ['claim-key', identity(parts[0]), parts[1]] + [identity(v) for v in parts[2:]]
        if key in SEQUENCES and type(value) is int and value >= 0:
            return ['sequence-rank', ranks[value]]
        if isinstance(value, dict):
            return {k: walk(v, k) for k, v in sorted(value.items())}
        if isinstance(value, list):
            return [walk(v) for v in value]
        return value
    return json.dumps(walk(observation), ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)
