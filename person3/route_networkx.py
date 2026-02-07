#!/usr/bin/env python3
"""Build a NetworkX graph from backend road geometry + risk and compute a least-risk path.

Usage: python person3/route_networkx.py --bbox west south east north --origin lon,lat --dest lon,lat
If origin/dest omitted, the script will pick two distant nodes from the graph and compute a route.
"""
import sys
import json
import math
import argparse
from urllib.parse import urlencode
import requests
import networkx as nx

DEF_BACKEND = 'http://127.0.0.1:5001'


def haversine_m(lon1, lat1, lon2, lat2):
    # returns distance in meters
    R = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2.0)**2 + math.cos(phi1)*math.cos(phi2)*(math.sin(dlambda/2.0)**2)
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1-a)))


def build_graph_from_bbox(west, south, east, north, backend_url=DEF_BACKEND, risk_penalty=5.0):
    # fetch geometry
    geom_url = backend_url + '/api/roads_bbox'
    r = requests.post(geom_url, json={'bbox':[west, south, east, north]}, timeout=30)
    r.raise_for_status()
    geom = r.json()

    # fetch risk map
    risk_url = backend_url + '/api/roads_risk?bbox=' + urlencode({ 'bbox': f'{west},{south},{east},{north}' })
    # simpler: call endpoint without urlencode
    risk_url = backend_url + '/api/roads_risk?bbox=%s' % (','.join(map(str, [west, south, east, north])))
    rr = requests.get(risk_url, timeout=30)
    rr.raise_for_status()
    rj = rr.json()
    riskMap = {}
    if rj and rj.get('roads'):
        if isinstance(rj['roads'], list):
            for it in rj['roads']:
                riskMap[str(it.get('id'))] = it
        else:
            for k,v in rj['roads'].items():
                rid = str(v.get('id') or k)
                riskMap[rid] = v

    G = nx.Graph()
    def key(lon, lat):
        return f"{lon:.5f},{lat:.5f}"

    for feat in geom.get('features', []):
        if not feat.get('geometry') or feat['geometry'].get('type') != 'LineString':
            continue
        coords = feat['geometry'].get('coordinates', [])
        rid = str(feat.get('id') or (feat.get('properties') or {}).get('id') or '')
        risk_val = 0.0
        if rid and rid in riskMap:
            try:
                risk_val = float(riskMap[rid].get('risk', 0.0))
            except Exception:
                risk_val = 0.0

        for i in range(len(coords)-1):
            a = coords[i]; b = coords[i+1]
            ka = key(a[0], a[1]); kb = key(b[0], b[1])
            if not G.has_node(ka): G.add_node(ka, lon=a[0], lat=a[1])
            if not G.has_node(kb): G.add_node(kb, lon=b[0], lat=b[1])
            length = haversine_m(a[0], a[1], b[0], b[1])
            # weight favors low-risk: we make weight = length * (1 + risk * penalty)
            weight = length * (1.0 + risk_val * float(risk_penalty))
            # store attributes
            if G.has_edge(ka, kb):
                # keep smaller weight if multiple parallels
                if weight < G[ka][kb]['weight']:
                    G[ka][kb].update({'weight': weight, 'length': length, 'risk': risk_val})
            else:
                G.add_edge(ka, kb, weight=weight, length=length, risk=risk_val)

    return G


def nearest_node_key(G, lon, lat):
    best = None; best_d = float('inf')
    for n, d in G.nodes(data=True):
        d_m = haversine_m(lon, lat, d['lon'], d['lat'])
        if d_m < best_d:
            best_d = d_m; best = n
    return best, best_d


def compute_route_from_bbox(bbox, origin, dest):
    west,south,east,north = bbox
    G = build_graph_from_bbox(west,south,east,north)
    print('graph nodes', G.number_of_nodes(), 'edges', G.number_of_edges())
    o_k, od = nearest_node_key(G, origin[0], origin[1])
    d_k, dd = nearest_node_key(G, dest[0], dest[1])
    print('origin nearest:', o_k, 'dist_m', int(od), 'dest nearest:', d_k, 'dist_m', int(dd))
    if o_k is None or d_k is None:
        print('No nearby graph nodes')
        return
    try:
        path = nx.dijkstra_path(G, source=o_k, target=d_k, weight='weight')
    except nx.NetworkXNoPath:
        print('No path found between nodes')
        return
    coords = [[G.nodes[n]['lon'], G.nodes[n]['lat']] for n in path]
    total_weight = sum(G[path[i]][path[i+1]]['weight'] for i in range(len(path)-1))
    print('path length nodes:', len(path), 'total_weight:', total_weight)
    print(json.dumps({'path': coords, 'total_weight': total_weight}, indent=2))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--bbox', help='west south east north', nargs=4, type=float)
    p.add_argument('--origin', help='lon,lat', default=None)
    p.add_argument('--dest', help='lon,lat', default=None)
    p.add_argument('--backend', help='backend base url', default=DEF_BACKEND)
    p.add_argument('--penalty', help='risk penalty multiplier', default=5.0, type=float)
    args = p.parse_args()
    if not args.bbox:
        print('Please supply --bbox W S E N')
        sys.exit(1)
    bbox = tuple(args.bbox)
    if args.origin:
        olon, olat = map(float, args.origin.split(','))
    else:
        # pick two nodes far apart from bbox center
        olon = (bbox[0] + bbox[2]) / 2.0; olat = (bbox[1] + bbox[3]) / 2.0
        olon += 0.0005; olat += 0.0005
    if args.dest:
        dlon, dlat = map(float, args.dest.split(','))
    else:
        dlon = (bbox[0] + bbox[2]) / 2.0; dlat = (bbox[1] + bbox[3]) / 2.0
        dlon -= 0.0005; dlat -= 0.0005
    compute_route_from_bbox(bbox, (olon, olat), (dlon, dlat))


if __name__ == '__main__':
    main()
