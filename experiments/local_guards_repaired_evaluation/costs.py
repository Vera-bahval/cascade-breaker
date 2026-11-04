"""Retrospective request accounting; does not price future/local computation."""
from decimal import Decimal
from .run import HERE
from experiments.local_guards_adapter_repair.inventory import rows,sha,write_json


def total(records):
    return dict(states=len(records),unique_queries=len({r['query_id'] for r in records}),
        historical_actual_eliza_charge_usd=str(sum((Decimal(str(r['charge_usd'])) for r in records),Decimal(0)).quantize(Decimal('0.000000001'))),
        usage={field:sum(r['usage'].get(field,0) for r in records)
             for field in ('prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens')})


def run():
    saved={r['prefix_id']:r for r in rows(HERE/'results/saved-deepseek.jsonl.gz')}
    methods=('v3|rule|A','v4.3|rule|A','native|rule|A','native_core|rule|A')
    blocked={m:set() for m in methods}
    for r in rows(HERE/'results/p4-decisions.jsonl.gz'):
        if r['mode']=='common' and r['config'] in blocked and r['decision']=='BLOCK':
            blocked[r['config']].add(r['prefix_id'])
    write_json(HERE/'cost-accounting.json',dict(new_llm_api_calls=0,new_eliza_charge_usd='0',
        local_computation_price=None,reference=total(list(saved.values())),
        block_only_cascade={m:dict(skipped_old_answers=total([saved[p] for p in sorted(ids)]),
            retained_old_answers=total([r for p,r in saved.items() if p not in ids])) for m,ids in blocked.items()},
        interpretation='Amounts are past actual charges on frozen inputs, not measured savings or a forecast of cache/cascade behaviour.',
        source_sha256=sha(HERE/'results/saved-deepseek.jsonl.gz')))


if __name__=='__main__':run()
