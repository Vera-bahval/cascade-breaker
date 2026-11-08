"""Full archived-task clock reconstruction; never sums nested tool durations."""
import math
from statistics import mean,median


def union_ms(intervals):
    total=0.;left=right=None
    for a,b in sorted(intervals):
        if b<a:raise ValueError('negative interval')
        if left is None:left,right=a,b
        elif a<=right:right=max(right,b)
        else:total+=right-left;left,right=a,b
    return total+(right-left if left is not None else 0)


def stats(values):
    values=sorted(values)
    return dict(n=len(values),mean_s=mean(values) if values else None,
        median_s=median(values) if values else None,
        p95_s=values[math.ceil(.95*len(values))-1] if values else None)


def clock(record):
    pauses=[];envelopes=[];before=[];before_env=[];steps=record['steps'];cut=record['cut_seq']
    context=next(s for s in steps if s['seq']==cut)
    for i,s in enumerate(steps):
        if s['kind']!='guard_context':continue
        end=s['t_ms'];a=end-s['pause_ms']
        if a<-.1:raise ValueError('negative check start')
        following=next((x for x in steps[i+1:] if x['kind']!='guard'),None)
        if following is None:raise ValueError('no post-check boundary')
        interval=(a,end);pauses.append(interval)
        env=(steps[i-1]['t_ms'] if i else 0,following.get('t_start_ms',following['t_ms']))
        if env[1]<env[0]:raise ValueError('invalid surrounding check interval')
        envelopes.append(env)
        if s['seq']<=cut:before.append(interval);before_env.append(env)
    p=union_ms(pauses);e=union_ms(envelopes)
    result=dict(observed_s=record['wall_s'],pause_ms=p,envelope_ms=e,
        complete_s=record['wall_s']-p/1000,complete_lower_s=record['wall_s']-e/1000,
        stop_s=(context['t_ms']-union_ms(before))/1000,
        stop_lower_s=(context['t_ms']-union_ms(before_env))/1000,
        rounding_bound_s=(5+.05*len(pauses))/1000,checks=len(pauses),
        pause_sum_ms=sum(b-a for a,b in pauses),cut_seq=cut,cut_point=context.get('point'),
        wall_minus_last_event_ms=record['wall_s']*1000-steps[-1]['t_ms'])
    if min(result['complete_lower_s'],result['stop_lower_s'])<0:raise ValueError('negative reconstructed time')
    return result
