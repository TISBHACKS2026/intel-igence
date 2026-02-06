from flask import Flask, jsonify, send_from_directory, redirect, make_response, request
from flask_cors import CORS
import os
import sys
import traceback
import requests

# Ensure project root is on sys.path so modules at repo root (like roadrisk.py)
# can be imported when the server is started from the backend/ directory.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

app = Flask(__name__, static_folder=None)
# Allow CORS for API endpoints (lib handles simple cases)
CORS(app)


@app.route('/api/roads_flood_risk')
def roads():
    # Minimal sample GeoJSON with a few LineString segments near Indiranagar
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "r1",
                "properties": {"flood_risk": 0.1},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [77.6395, 12.9725],
                        [77.6410, 12.9710]
                    ]
                }
            },
            {
                "type": "Feature",
                "id": "r2",
                "properties": {"flood_risk": 0.9},
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [77.6415, 12.9730],
                        [77.6430, 12.9720]
                    ]
                }
            }
        ]
    }
    # Build response and ensure explicit CORS headers for browsers and preflight
    resp = make_response(jsonify(geojson))
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return resp


@app.route('/api/roads_flood_risk', methods=['OPTIONS'])
def roads_options():
    # Reply to CORS preflight explicitly
    resp = make_response('')
    resp.headers['Access-Control-Allow-Origin'] = '*'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return resp


# Serve frontend static files so the demo can be loaded from the same origin
@app.route('/frontend/<path:filename>')
def frontend_files(filename):
    base = os.path.join(os.path.dirname(__file__), '..')
    frontend_dir = os.path.abspath(os.path.join(base, 'frontend'))
    return send_from_directory(frontend_dir, filename)


@app.route('/')
def index():
    # Redirect to the demo HTML when visiting the backend root
    return redirect('/frontend/cesium_viewer.html')


@app.route('/api/elevation', methods=['POST'])
def elevation():
    """Sample elevation values for a list of [lon, lat] points.

    Request JSON: { "points": [[lon, lat], ...] }
    Response JSON: { "elevations": [z1, z2, ...] }
    """
    try:
        data = request.get_json(force=True)
        pts = data.get('points') if data else None
        if not pts or not isinstance(pts, list):
            resp = make_response(jsonify({'error': 'Send JSON with a "points" array [[lon,lat],...]'}), 400)
            resp.headers['Access-Control-Allow-Origin'] = '*'
            return resp

        # Look for a local HGT file (SRTM) in the repo spool
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        # This example targets the bundled N12/N12E077.hgt file (Bengaluru area)
        hgt_path = os.path.join(base, 'spool', 'N12', 'N12E077.hgt')
        if not os.path.exists(hgt_path):
            resp = make_response(jsonify({'error': 'HGT file not found on server', 'path': hgt_path}), 500)
            resp.headers['Access-Control-Allow-Origin'] = '*'
            return resp

        # Use rasterio if available to sample elevations; if rasterio missing, return error
        try:
            import rasterio
        except Exception as e:
            resp = make_response(jsonify({'error': 'rasterio not installed on server', 'detail': str(e)}), 500)
            resp.headers['Access-Control-Allow-Origin'] = '*'
            return resp

        elevations = []
        with rasterio.open(hgt_path) as ds:
            # rasterio expects (lon, lat) order for sampling in geographic datasets
            for p in pts:
                try:
                    lon, lat = float(p[0]), float(p[1])
                    for val in ds.sample([(lon, lat)]):
                        z = float(val[0]) if val is not None and len(val) and val[0] is not None else None
                        elevations.append(z)
                except Exception:
                    elevations.append(None)

        resp = make_response(jsonify({'elevations': elevations}))
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp
    except Exception as e:
        traceback.print_exc()
        resp = make_response(jsonify({'error': 'internal server error', 'detail': str(e)}), 500)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp


@app.route('/api/roads_bbox', methods=['POST'])
def roads_bbox():
    """Query OpenStreetMap (Overpass) for roads within a bbox.

    Request JSON: { "bbox": [west, south, east, north] }
    Response: GeoJSON FeatureCollection of LineString ways with id and tags
    """
    try:
        data = request.get_json(force=True)
        if not data:
            return make_response(jsonify({'error': 'expected JSON body with bbox'}), 400)
        bbox = data.get('bbox')
        if not bbox or not (isinstance(bbox, list) and len(bbox) == 4):
            return make_response(jsonify({'error': 'bbox required as [west,south,east,north]'}), 400)
        west, south, east, north = map(float, bbox)

        # Try several Overpass mirrors in order until one succeeds
        mirrors = [
            'https://overpass-api.de/api/interpreter',
            'https://lz4.overpass-api.de/api/interpreter',
            'https://overpass.kumi.systems/api/interpreter'
        ]
        q = f'[out:json][timeout:25];(way["highway"]({south},{west},{north},{east}););out geom;'
        headers = {'Content-Type': 'text/plain'}
        ov = None
        last_err = None
        for overpass_url in mirrors:
            try:
                r = requests.post(overpass_url, data=q.encode('utf-8'), headers=headers, timeout=30)
                if r.status_code == 200:
                    ov = r.json()
                    break
                else:
                    last_err = f'status {r.status_code} from {overpass_url}'
            except Exception as e:
                last_err = str(e)
                continue
        if ov is None:
            return make_response(jsonify({'error': 'overpass endpoints failed', 'detail': last_err}), 502)
        features = []
        for el in ov.get('elements', []):
            if el.get('type') != 'way':
                continue
            geom = el.get('geometry')
            if not geom:
                continue
            coords = [[pt['lon'], pt['lat']] for pt in geom]
            feat = {
                'type': 'Feature',
                'id': str(el.get('id')),
                'properties': el.get('tags') or {},
                'geometry': {
                    'type': 'LineString',
                    'coordinates': coords
                }
            }
            features.append(feat)

        geojson = {'type': 'FeatureCollection', 'features': features}
        resp = make_response(jsonify(geojson))
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp
    except Exception as e:
        traceback.print_exc()
        resp = make_response(jsonify({'error': 'internal server error', 'detail': str(e)}), 500)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp


@app.route('/api/roads_risk', methods=['GET', 'POST'])
def roads_risk():
    """Return the precomputed per-road risk JSON.

    If an optional bbox is provided (either as a GET query `bbox=west,south,east,north`
    or as POST JSON `{ "bbox": [west,south,east,north] }`) the endpoint will
    query Overpass for ways inside that bbox and return only the matching road
    records as a dictionary keyed by road id: `{ "roads": { id: record, ... } }`.

    Without a bbox the endpoint preserves the original behavior and returns
    the full array under `roads`.
    """
    try:
        # Allow dynamic computation using roadrisk.py when available.
        # Parse optional bbox from GET query or POST JSON
        bbox = None
        if request.method == 'GET':
            bbox_q = request.args.get('bbox')
            if bbox_q:
                try:
                    parts = [float(x) for x in bbox_q.split(',')]
                    if len(parts) == 4:
                        bbox = parts
                except Exception:
                    bbox = None
        else:
            body = request.get_json(silent=True) or {}
            b = body.get('bbox')
            if isinstance(b, (list, tuple)) and len(b) == 4:
                try:
                    bbox = [float(x) for x in b]
                except Exception:
                    bbox = None
        # Accept optional rain parameter for dynamic computation
        rain_param = None
        try:
            if request.method == 'GET':
                rain_param = request.args.get('rain_mm')
            else:
                rain_param = (body.get('rain_mm') if body else None)
            if rain_param is not None:
                rain_param = float(rain_param)
        except Exception:
            rain_param = None

        # Try to import roadrisk and compute dynamically; fall back to static file when unavailable
        computed = None
        try:
            import roadrisk
            rain_val = float(rain_param) if rain_param is not None else 50.0
            computed = roadrisk.compute_all_roads(rain_mm=rain_val)
        except Exception:
            # fallback: load precomputed file
            base = os.path.abspath(os.path.join(os.path.dirname(__file__), '.'))
            path = os.path.join(base, 'roads_with_risk.json')
            if not os.path.exists(path):
                return make_response(jsonify({'error': 'roads_with_risk.json not found on server and roadrisk import failed', 'path': path}), 404)
            import json
            with open(path, 'r', encoding='utf-8') as fh:
                computed = json.load(fh)

        # Normalize computed into a list of dicts
        if isinstance(computed, dict):
            # assume {'roads': ...}
            comp_list = computed.get('roads') if 'roads' in computed else list(computed.values())
        else:
            comp_list = computed

        if not bbox:
            # No bbox — return computed array
            resp = make_response(jsonify({'roads': comp_list}))
            resp.headers['Access-Control-Allow-Origin'] = '*'
            return resp

        # If bbox present, query Overpass to get the set of way ids in bbox
        west, south, east, north = map(float, bbox)
        mirrors = [
            'https://overpass-api.de/api/interpreter',
            'https://lz4.overpass-api.de/api/interpreter',
            'https://overpass.kumi.systems/api/interpreter'
        ]
        q = f'[out:json][timeout:25];(way["highway"]({south},{west},{north},{east}););out ids;'
        headers = {'Content-Type': 'text/plain'}
        ov = None
        last_err = None
        for overpass_url in mirrors:
            try:
                r = requests.post(overpass_url, data=q.encode('utf-8'), headers=headers, timeout=30)
                if r.status_code == 200:
                    ov = r.json()
                    break
                else:
                    last_err = f'status {r.status_code} from {overpass_url}'
            except Exception as e:
                last_err = str(e)
                continue
        if ov is None:
            return make_response(jsonify({'error': 'overpass endpoints failed', 'detail': last_err}), 502)

        way_ids = set()
        for el in ov.get('elements', []):
            if el.get('type') == 'way':
                way_ids.add(str(el.get('id')))

        # Filter computed list by ids present in bbox and return dict keyed by id
        filtered = {str(r.get('id')): r for r in (comp_list or []) if str(r.get('id')) in way_ids}

        resp = make_response(jsonify({'roads': filtered}))
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp
    except Exception as e:
        traceback.print_exc()
        resp = make_response(jsonify({'error': 'internal server error', 'detail': str(e)}), 500)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp


@app.route('/api/save_roads_risk', methods=['POST'])
def save_roads_risk():
    """Save a provided roads array to backend/roads_with_risk.json.

    Expects JSON: { "roads": [ {id:..., risk:..., ...}, ... ] }
    This is a convenience for the demo so the selected subset can be persisted.
    """
    try:
        data = request.get_json(force=True)
        if not data or 'roads' not in data:
            return make_response(jsonify({'error': 'expected JSON with "roads" array'}), 400)
        roads = data.get('roads')
        if not isinstance(roads, list):
            return make_response(jsonify({'error': 'roads must be an array'}), 400)
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), '.'))
        path = os.path.join(base, 'roads_with_risk.json')
        import json
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(roads, fh, indent=2, ensure_ascii=False)
        resp = make_response(jsonify({'ok': True, 'written': len(roads), 'path': path}))
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp
    except Exception as e:
        traceback.print_exc()
        resp = make_response(jsonify({'error': 'internal server error', 'detail': str(e)}), 500)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp


@app.route('/api/roadrisk_source', methods=['GET'])
def roadrisk_source():
    """Return the source of roadrisk.py as plain text for the demo."""
    try:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
        path = os.path.join(base, 'roadrisk.py')
        if not os.path.exists(path):
            resp = make_response(jsonify({'error': 'roadrisk.py not found', 'path': path}), 404)
            resp.headers['Access-Control-Allow-Origin'] = '*'
            return resp
        with open(path, 'r', encoding='utf-8') as fh:
            txt = fh.read()
        resp = make_response(txt)
        resp.headers['Content-Type'] = 'text/plain; charset=utf-8'
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp
    except Exception as e:
        traceback.print_exc()
        resp = make_response(jsonify({'error': 'internal server error', 'detail': str(e)}), 500)
        resp.headers['Access-Control-Allow-Origin'] = '*'
        return resp


if __name__ == '__main__':
    # Development server: allow overriding the port via the PORT env var
    try:
        port = int(os.environ.get('PORT', '5100'))
    except Exception:
        port = 5100
    app.run(host='0.0.0.0', port=port, debug=True)
