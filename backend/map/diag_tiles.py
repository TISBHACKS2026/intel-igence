#!/usr/bin/env python3
import math, json, os
import osmnx as ox
from PIL import Image

def _deg2num(lat_deg, lon_deg, zoom):
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = (lon_deg + 180.0) / 360.0 * n
    ytile = (1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n
    return xtile, ytile

def lonlat_to_global_px(lon, lat, zoom, tile_size=256):
    n = 2 ** zoom
    x = (lon + 180.0) / 360.0 * n * tile_size
    lat_rad = math.radians(lat)
    y = (1 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2 * n * tile_size
    return x, y

def main():
    G = ox.load_graphml('backend/map/data/graph.graphml')
    nodes, edges = ox.graph_to_gdfs(G)
    minx, miny, maxx, maxy = nodes.total_bounds
    west, south, east, north = minx, miny, maxx, maxy
    zoom = 17

    x_min_f, y_max_f = _deg2num(north, west, zoom)
    x_max_f, y_min_f = _deg2num(south, east, zoom)
    x_min = int(math.floor(x_min_f))
    x_max = int(math.floor(x_max_f))
    y_min = int(math.floor(y_min_f))
    y_max = int(math.floor(y_max_f))
    nx_tiles = x_max - x_min + 1
    ny_tiles = y_max - y_min + 1
    tiles_count = nx_tiles * ny_tiles

    px_min, py_max = lonlat_to_global_px(west, north, zoom)
    px_max, py_min = lonlat_to_global_px(east, south, zoom)
    origin_x = x_min * 256
    origin_y = y_min * 256
    left = int(px_min - origin_x)
    upper = int(py_min - origin_y)
    right = int(px_max - origin_x)
    lower = int(py_max - origin_y)

    tex_path = 'backend/map/data/texture.png'
    size_info = None
    if os.path.exists(tex_path):
        im = Image.open(tex_path)
        size_info = im.size

    out = {
        'bbox_west_south_east_north': [west, south, east, north],
        'zoom': zoom,
        'tile_x_range': [x_min, x_max],
        'tile_y_range': [y_min, y_max],
        'tiles_count': tiles_count,
        'stitched_pixel_size': [nx_tiles*256, ny_tiles*256],
        'crop_box_in_stitched_px': [left, upper, right, lower],
        'texture_exists': os.path.exists(tex_path),
        'texture_size': size_info,
        'texture_path': tex_path
    }
    print(json.dumps(out, indent=2))

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print('ERROR:', e)
