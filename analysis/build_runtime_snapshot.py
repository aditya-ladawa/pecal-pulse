"""Stream the full extract into a small API snapshot plus indexed evidence store.

No customer sampling: account/history totals are preserved. Raw instrument events
stay in the source; all requirement evidence is available on demand in SQLite.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta
import json
from pathlib import Path
import sqlite3
import ijson

ROOT = Path(__file__).resolve().parents[1]

def rows(path, section):
    with path.open('rb') as source:
        yield from ijson.items(source, section + '.item', use_float=True)

def build(snapshot_id, folder=None):
    folder = folder or ROOT / 'data/runtime/snapshots'
    source = folder / f'{snapshot_id}.json'
    with source.open('rb') as f:
        manifest = next(ijson.items(f, 'manifest', use_float=True))
    reference = date.fromisoformat(manifest['reference_date'])
    first, last = str(reference-timedelta(days=90)), str(reference+timedelta(days=90))
    compact = {'manifest':manifest, 'runtime_compact':True, 'instruments':[], 'events':[]}
    for section in ('profiles','history','portfolio','month_grid','industry_labels','equipment_group_labels'):
        compact[section] = list(rows(source,section))
        print(section,len(compact[section]),flush=True)
    counts, groups = Counter(), defaultdict(set)
    for inst in rows(source,'instruments'):
        cid=inst.get('current_customer_id')
        if cid:
            counts[cid]+=1
            if inst.get('group_id'): groups[cid].add(inst['group_id'])
    compact['ranking_instrument_counts']=dict(counts)
    compact['customer_group_ids']={cid:sorted(values) for cid,values in groups.items()}
    store = folder / f'{snapshot_id}.requirements.sqlite3'
    temp = store.with_suffix('.tmp')
    db=sqlite3.connect(temp)
    db.execute('DROP TABLE IF EXISTS requirements')
    db.execute('CREATE TABLE requirements(customer_id TEXT, id TEXT, kind TEXT, payload TEXT)')
    db.execute('PRAGMA journal_mode=OFF')
    kinds, by_customer, eligible, near, batch = Counter(), defaultdict(Counter), 0, [], []
    for r in rows(source,'requirements'):
        kinds[r['kind']]+=1;by_customer[r['customer_id']][r['kind']]+=1
        eligible += r['eligibility']=='eligible'
        batch.append((r['customer_id'],r['id'],r['kind'],json.dumps(r,separators=(',',':'))))
        if len(batch)>=2000:
            db.executemany('INSERT INTO requirements VALUES (?,?,?,?)',batch);batch.clear()
        if r.get('window_start') and r.get('window_end') and r['kind']!='unknown' and r['eligibility']!='excluded' and r.get('stopped') is not True:
            if r['window_end']>=first and r['window_start']<=last and r['window_end']>=r['window_start']:
                near.append(r)
    if batch: db.executemany('INSERT INTO requirements VALUES (?,?,?,?)',batch)
    db.execute('CREATE INDEX customer_requirements ON requirements(customer_id)')
    db.commit();db.close();temp.replace(store)
    compact['requirements']=near
    compact['requirement_summary']={'by_kind':dict(kinds),'eligible':eligible,'by_customer':dict(by_customer)}
    output=folder/f'{snapshot_id}.compact.json'
    temp=output.with_suffix('.tmp')
    with temp.open('w') as f: json.dump(compact,f,separators=(',',':'),allow_nan=False)
    temp.replace(output)
    print(json.dumps({'compact_mb':round(output.stat().st_size/1024**2,1),'accounts':len(compact['profiles']),
        'history_rows':len(compact['history']),'runtime_requirements':len(near),'full_evidence_rows':sum(kinds.values())}),flush=True)
    return output

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--snapshot-id',required=True)
    args=parser.parse_args();build(args.snapshot_id)
if __name__=='__main__':main()
