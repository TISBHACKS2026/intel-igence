"""Fetch OSM road network and export to backend/map/data

Usage:
    python fetch_map.py --place "Indiranagar, Bangalore, India"
"""
from typing import Optional, Tuple
import os
import argparse
import osmnx as ox


def fetch_roads(place: Optional[str] = None, bbox: Optional[Tuple[float, float, float, float]] = None,
                network_type: str = "drive", out_dir: str = "backend/map/data"):
    os.makedirs(out_dir, exist_ok=True)
    if place:
        G = ox.graph_from_place(place, network_type=network_type)
    elif bbox:
        north, south, east, west = bbox
        G = ox.graph_from_bbox(north, south, east, west, network_type=network_type)
    else:
        raise ValueError("Either `place` or `bbox` must be provided")

    graphml_path = os.path.join(out_dir, "graph.graphml")
    ox.save_graphml(G, graphml_path)

    # also save edges/nodes as GeoDataFrames
    nodes, edges = ox.graph_to_gdfs(G)
    nodes.to_file(os.path.join(out_dir, "nodes.geojson"), driver="GeoJSON")
    edges.to_file(os.path.join(out_dir, "edges.geojson"), driver="GeoJSON")

    return G


def _cli():
    p = argparse.ArgumentParser()
    p.add_argument("--place", help="Place name for OSM (e.g. 'Indiranagar, Bangalore, India')")
    p.add_argument("--network", default="drive", help="OSM network type (drive, walk, all)")
    args = p.parse_args()
    fetch_roads(place=args.place, network_type=args.network)


if __name__ == "__main__":
    _cli()
