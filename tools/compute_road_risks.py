#!/usr/bin/env python3
"""Compute road risk input records from a GeoJSON FeatureCollection of roads.

Usage:
  python tools/compute_road_risks.py input_roads.geojson > roads_risk.json

Output: JSON array of objects with keys: id, length (meters), avg_elevation,
min_elev, max_elev
"""
import json
import os
import sys
from math import ceil

from pyproj import Geod

GEOD = Geod(ellps="WGS84")


def geodesic_length(coords):
    """Return length in meters for a sequence of (lon,lat) coords."""
    total = 0.0
    for a, b in zip(coords[:-1], coords[1:]):
        lon1, lat1 = a
        lon2, lat2 = b
        _, _, dist = GEOD.inv(lon1, lat1, lon2, lat2)
        total += dist
    return total


def densify_coords(coords, max_segment_m=10.0):
    """Return a list of coords with intermediate points so no segment > max_segment_m."""
    out = []
    for a, b in zip(coords[:-1], coords[1:]):
        out.append(a)
        lon1, lat1 = a
        lon2, lat2 = b
        _, _, dist = GEOD.inv(lon1, lat1, lon2, lat2)
        if dist > max_segment_m:
            steps = int(ceil(dist / max_segment_m))
            for s in range(1, steps):
                frac = s / steps
                out.append((lon1 + (lon2 - lon1) * frac, lat1 + (lat2 - lat1) * frac))
    out.append(coords[-1])
    return out


def find_hgt_file(spool_dir="spool"):
    # look for any .hgt file under spool
    for root, _dirs, files in os.walk(spool_dir):
        for f in files:
            if f.lower().endswith(".hgt"):
                return os.path.join(root, f)
    return None


def sample_elevations_raster(coords, hgt_path):
    try:
        import rasterio
    except Exception:
        return [None] * len(coords)

    with rasterio.open(hgt_path) as ds:
        vals = []
        for lon, lat in coords:
            try:
                rowcol = ds.index(lon, lat)
                v = ds.read(1)[rowcol[0], rowcol[1]]
                if v == ds.nodata:
                    vals.append(None)
                else:
                    vals.append(float(v))
            except Exception:
                vals.append(None)
        return vals


def compute_record(feature, hgt_path=None):
    geom = feature.get("geometry") or {}
    props = feature.get("properties", {})
    fid = props.get("osmid") or props.get("id") or feature.get("id")
    coords = []
    if not geom:
        return None
    gtype = geom.get("type")
    if gtype == "LineString":
        coords = geom.get("coordinates", [])
    elif gtype == "MultiLineString":
        # flatten
        parts = geom.get("coordinates", [])
        if parts:
            coords = [pt for part in parts for pt in part]
    else:
        return None

    if len(coords) < 2:
        return None

    length_m = geodesic_length(coords)

    samp_coords = densify_coords(coords, max_segment_m=10.0)
    elevations = None
    if hgt_path:
        elevations = sample_elevations_raster(samp_coords, hgt_path)
    else:
        elevations = [None] * len(samp_coords)

    numeric = [v for v in elevations if v is not None]
    if numeric:
        avg_elev = sum(numeric) / len(numeric)
        min_elev = min(numeric)
        max_elev = max(numeric)
    else:
        avg_elev = None
        min_elev = None
        max_elev = None

    return {
        "id": fid,
        "length": round(length_m, 2),
        "avg_elevation": None if avg_elev is None else round(avg_elev, 2),
        "min_elev": None if min_elev is None else round(min_elev, 2),
        "max_elev": None if max_elev is None else round(max_elev, 2),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: compute_road_risks.py input_roads.geojson > roads_risk.json", file=sys.stderr)
        sys.exit(2)

    inpath = sys.argv[1]
    with open(inpath, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    hgt = find_hgt_file()
    if hgt is None:
        # no HGT available — proceed but elevations will be None
        hgt = None

    out = []
    features = data.get("features", []) if isinstance(data, dict) else []
    for feat in features:
        rec = compute_record(feat, hgt)
        if rec:
            out.append(rec)

    json.dump(out, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
