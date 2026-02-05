**Map + Elevation + Road Graph**

Purpose: extract OSM roads for Indiranagar, sample elevations (SRTM), and build a road
graph with `length` and `avg_elevation` per edge.

Quick start

- Fetch roads:
```bash
python backend/map/fetch_map.py --place "Indiranagar, Bangalore, India"
```
- Build enriched graph (requires a local SRTM GeoTIFF):
```bash
python backend/map/road_graph.py --srtm /path/to/srtm.tif --graph backend/map/data/graph.graphml
```

Outputs (in `backend/map/data`): `graph.graphml`, `graph.pkl`, `graph.json`, `nodes.geojson`, `edges.geojson`.

Notes
- Scripts assume coordinates in (lon, lat) / EPSG:4326. If your SRTM is in another CRS the code
  will attempt to transform coordinates before sampling.
- Install dependencies from the repository `requirements.txt` before running.
