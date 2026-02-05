"""Elevation sampling utilities using rasterio.

Functions here assume point coordinates are lon/lat (EPSG:4326). If the raster
is in a different CRS, the code will transform coordinates to the raster CRS.
"""
from typing import Iterable, List, Optional
import rasterio
from rasterio.warp import transform
from shapely.geometry import LineString, Point
import numpy as np


def _transform_coords_if_needed(points: Iterable[tuple], src_crs: Optional[str], dst_crs):
    # points: sequence of (lon, lat) in EPSG:4326
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    if dst_crs is None:
        return list(zip(xs, ys))
    dst = dst_crs
    if dst.to_string() == "EPSG:4326":
        return list(zip(xs, ys))
    tx, ty = transform("EPSG:4326", dst, xs, ys)
    return list(zip(tx, ty))


def sample_elevations(points: Iterable[tuple], raster_path: str) -> List[Optional[float]]:
    """Sample raster elevations for a list of (lon, lat) points.

    Returns list of floats or None for nodata.
    """
    with rasterio.open(raster_path) as src:
        dst_crs = src.crs
        coords = _transform_coords_if_needed(points, "EPSG:4326", dst_crs)
        results = []
        for val in src.sample(coords):
            v = val[0]
            if v == src.nodata:
                results.append(None)
            else:
                results.append(float(v))
    return results


def avg_elevation_for_line(line: LineString, raster_path: str, n_samples: int = 5) -> Optional[float]:
    """Sample `n_samples` points along the LineString and return the average elevation.

    Returns None if all samples are nodata.
    """
    if line.is_empty:
        return None
    if n_samples <= 1:
        n_samples = 2
    distances = np.linspace(0, line.length, n_samples)
    pts = [line.interpolate(d) for d in distances]
    coords = [(p.x, p.y) for p in pts]
    elevs = sample_elevations(coords, raster_path)
    valid = [e for e in elevs if e is not None]
    if not valid:
        return None
    return float(sum(valid) / len(valid))


__all__ = ["sample_elevations", "avg_elevation_for_line"]
