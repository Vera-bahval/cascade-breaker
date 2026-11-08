"""Keep original old400 requirement labels verbatim in derived scoring inputs.

The generic archival custodian is not the fixture oracle: its A08 overwrite is
inappropriate when original reviewed fixture labels already exist. No methods,
predictions, original files or v4.2 labels are changed here.
"""
from pathlib import Path
from .evaluate import read_rows,write_rows,write_json,digest


def run():
    here=Path(__file__).resolve().parent
    prior=here.with_name('local_guards_v4')/'closed/gold-actions.jsonl.gz'
    derived=here/'data/old400/gold-actions.jsonl.gz'
    originals={r['prefix_id']:r for r in read_rows(prior)}
    rows=read_rows(derived);changes=[]
    for row in rows:
        original=originals[row['prefix_id']]['requirements']
        if row['requirements_41']!=original:changes.append(row['prefix_id'])
        row['requirements_41']=original
    out=here/'data/old400/gold-original41.jsonl.gz'
    write_rows(out,rows)
    write_json(here/'data/old400/gold-original41.manifest.json',dict(
        input_hashes={str(p):digest(p) for p in [prior,derived]},
        output_sha256=digest(out),source_sha256=digest(Path(__file__)),
        corrected_requirement_rows=changes,original_requirements_verbatim=True,
        v42_labels_unchanged=True,predictions_read=False))


if __name__=='__main__':run()
