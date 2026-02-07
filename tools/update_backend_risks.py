#!/usr/bin/env python3
"""Recompute risks using roadrisk.compute_all_roads() and persist into backend/roads_with_risk.json
Writes `risk` and `level` fields for each road (matched by id); creates a backup.
Usage: python tools/update_backend_risks.py [rain_mm]
"""
import os, json, shutil, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
BACK = os.path.join(ROOT, 'backend', 'roads_with_risk.json')
if not os.path.exists(BACK):
    raise SystemExit('backend/roads_with_risk.json not found')

# import roadrisk module from repo root
import importlib
# Ensure repo root is on sys.path so `roadrisk` can be imported
sys.path.insert(0, ROOT)
spec = importlib.import_module('roadrisk')

rain = 50.0
if len(sys.argv) > 1:
    try:
        rain = float(sys.argv[1])
    except Exception:
        pass

computed = spec.compute_all_roads(rain_mm=rain)
# build map id->computed
comp_map = {str(r['id']): r for r in computed if r and r.get('id') is not None}

# backup
bak = BACK + '.bak2'
shutil.copy2(BACK, bak)

with open(BACK, 'r', encoding='utf-8') as fh:
    data = json.load(fh)

updated = 0
for rec in data:
    rid = str(rec.get('id'))
    if rid in comp_map:
        rec['risk'] = comp_map[rid].get('risk')
        rec['level'] = comp_map[rid].get('level')
        # also update avg_elevation if computed has it
        if comp_map[rid].get('avg_elevation') is not None:
            rec['avg_elevation'] = comp_map[rid].get('avg_elevation')
        updated += 1

with open(BACK, 'w', encoding='utf-8') as fh:
    json.dump(data, fh, indent=2, ensure_ascii=False)

print(f'Wrote {updated} records to {BACK}; backup at {bak}')
