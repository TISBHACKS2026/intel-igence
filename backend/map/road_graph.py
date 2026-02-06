"""Build a road graph enriched with elevation per edge.

Usage:
    python road_graph.py --srtm /path/to/srtm.tif --graph backend/map/data/graph.graphml
"""
import os
import argparse
from shapely.geometry import LineString
import networkx as nx
from networkx.readwrite import json_graph
import json
import osmnx as ox
# robust import: support running as module or as a script
try:
    from .elevation import avg_elevation_for_line
except Exception:
    # when executed as a script (python backend/map/road_graph.py), relative imports fail
    import os
    import argparse
    from shapely.geometry import LineString
    import networkx as nx
    from networkx.readwrite import json_graph
    import json
    import osmnx as ox
    import requests
    from time import sleep

    try:
        from .elevation import avg_elevation_for_line
    except Exception:
        from elevation import avg_elevation_for_line

def _line_from_edge(G, u, v, data):
    geom = data.get("geometry")
    if geom is not None:
        return geom
    # fallback: make a straight line from node coords
    xu = G.nodes[u].get("x")
    yu = G.nodes[u].get("y")
    xv = G.nodes[v].get("x")
    yv = G.nodes[v].get("y")
    return LineString([(xu, yu), (xv, yv)])


def _length_meters_for_line(line: LineString):
    coords = list(line.coords)
    if len(coords) < 2:
        return 0.0
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(coords, coords[1:]):
        total += ox.distance.great_circle_vec(lat1, lon1, lat2, lon2)
    return total


def enrich_graph_with_elevation(graph_path: str, srtm_path: str, out_dir: str = "backend/map/data"):
    os.makedirs(out_dir, exist_ok=True)
    # load graph
    if graph_path.lower().endswith(".graphml"):
        G = ox.load_graphml(graph_path)
    else:
        # try networkx gpickle
        G = nx.read_gpickle(graph_path)

    # helper: online elevation fallback
    def _online_avg_for_line(line: LineString, n_samples: int = 5):
        coords = []
        if line.is_empty:
            return None
        if n_samples <= 1:
            n_samples = 2
        distances = [i * (line.length / (n_samples - 1)) for i in range(n_samples)]
        pts = [line.interpolate(d) for d in distances]
        for p in pts:
            coords.append((p.y, p.x))  # latitude, longitude for API
        # batch request to open-elevation
        results = []
        batch_size = 100
        for i in range(0, len(coords), batch_size):
            chunk = coords[i:i+batch_size]
            locations = [{"latitude": lat, "longitude": lon} for lat, lon in chunk]
            try:
                resp = requests.post("https://api.open-elevation.com/api/v1/lookup", json={"locations": locations}, timeout=30)
                resp.raise_for_status()
                data = resp.json().get("results", [])
                for r in data:
                    results.append(r.get("elevation"))
            except Exception:
                # on error, append None for these
                results.extend([None] * len(chunk))
            sleep(0.1)
        valid = [r for r in results if r is not None]
        if not valid:
            return None
        return float(sum(valid) / len(valid))

    # iterate edges
    for u, v, key, data in G.edges(keys=True, data=True):
        line = _line_from_edge(G, u, v, data)
        length = data.get("length")
        if length is None:
            length = _length_meters_for_line(line)
        if srtm_path:
            avg_elev = avg_elevation_for_line(line, srtm_path, n_samples=5)
        else:
            avg_elev = _online_avg_for_line(line, n_samples=5)
        data["length"] = float(length)
        data["avg_elevation"] = None if avg_elev is None else float(avg_elev)

    # save serialized graph
    pkl_path = os.path.join(out_dir, "graph.pkl")
    json_path = os.path.join(out_dir, "graph.json")
    # write gpickle: networkx API changed across versions, fall back to pickle if needed
    try:
        nx.write_gpickle(G, pkl_path)
    except AttributeError:
        import pickle
        with open(pkl_path, "wb") as fh:
            pickle.dump(G, fh)
    node_link = json_graph.node_link_data(G)
    # make geometries JSON-serializable (convert shapely geometries to GeoJSON-like dicts)
    for link in node_link.get("links", []):
        geom = link.get("geometry")
        try:
            from shapely.geometry.base import BaseGeometry
        except Exception:
            BaseGeometry = None
        if BaseGeometry is not None and isinstance(geom, BaseGeometry):
            link["geometry"] = {"type": geom.geom_type, "coordinates": list(geom.coords)}
        else:
            # if it's a shapely-like object with coords attribute
            if hasattr(geom, "coords"):
                link["geometry"] = {"type": getattr(geom, "geom_type", "LineString"), "coordinates": list(geom.coords)}
    with open(json_path, "w", encoding="utf8") as fh:
        json.dump(node_link, fh)
    return G


def _cli():
    p = argparse.ArgumentParser()
    p.add_argument("--srtm", required=False, default=None, help="Path to SRTM (GeoTIFF) file for elevation sampling (optional). If omitted, uses online Open-Elevation API")
    p.add_argument("--graph", default="backend/map/data/graph.graphml", help="Input graph.graphml path")
    p.add_argument("--out", default="backend/map/data", help="Output data directory")
    args = p.parse_args()
    G = enrich_graph_with_elevation(args.graph, args.srtm, out_dir=args.out)
    print("Finished enriching graph. Saved to:", args.out)


if __name__ == "__main__":
    _cli()
