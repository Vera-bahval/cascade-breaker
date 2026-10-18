import hashlib,json
from pathlib import Path
from cascade_guard.night_rules_eval import rates,token_metadata

def test_hidden_suite_frozen_balanced():
    p=Path(__file__).resolve().parents[1]/'results/night-4b/rules-private'
    freeze=json.loads((p/'freeze.json').read_text());blob=(p/'cases.jsonl').read_bytes()
    assert hashlib.sha256(blob).hexdigest()==freeze['sha256']
    rows=[json.loads(x) for x in blob.splitlines()]
    assert len(rows)==64 and sum(x['expected_block'] for x in rows)==32
    assert len({x['case_id'] for x in rows})==64
    assert all('label' not in x['state'] for x in rows)

def test_metrics_do_not_mask_false_stops():
    r=rates([{'expected_block':False,'block':True},{'expected_block':True,'block':True}])
    assert r['false_stops']==1 and r['fpr']==1

def test_token_metadata_only_counters(tmp_path):
    p=tmp_path/'session.jsonl';p.write_text(json.dumps({'type':'response_item','payload':{'secret':'not output'}})+'\n'+json.dumps({'type':'event_msg','payload':{'type':'token_count','info':{'total_token_usage':{'input_tokens':10,'cached_input_tokens':3,'output_tokens':4,'reasoning_output_tokens':2,'total_tokens':14}}}})+'\n')
    r=token_metadata(p);assert r['total_tokens']==14 and r['reasoning_output_tokens_subset']==2
    assert 'secret' not in json.dumps(r)
