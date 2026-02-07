#!/usr/bin/env python3
"""Deterministically set `avg_elevation` per-road to a value in [890,915].
Uses an MD5-based hash of the road id so results are reproducible.
Creates a backup: `backend/roads_with_risk.json.bak`.
"""
import os, json, hashlib, shutil

base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
path = os.path.join(base, 'backend', 'roads_with_risk.json')
if not os.path.exists(path):
    raise SystemExit('roads_with_risk.json not found: ' + path)

bak = path + '.bak'
shutil.copy2(path, bak)

with open(path, 'r', encoding='utf-8') as fh:
    data = json.load(fh)

count = 0
for r in data:
    rid = str(r.get('id') or '')
    # deterministic pseudorandom fraction from id
    h = hashlib.md5(rid.encode('utf-8')).hexdigest()
    frac = (int(h[:8], 16) % 1000000) / 1000000.0
    elev = 890.0 + frac * (915.0 - 890.0)
    r['avg_elevation'] = round(elev, 2)
    count += 1

with open(path, 'w', encoding='utf-8') as fh:
    json.dump(data, fh, indent=2, ensure_ascii=False)

print(f'Updated {count} records; backup written to: {bak}')
