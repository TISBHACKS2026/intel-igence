"""Create a textured 3D terrain by draping a matplotlib-rendered map image
over the SRTM terrain and roads.

Outputs: backend/map/data/roads_draped.html
"""
import os
import rasterio
import numpy as np
import math
import io
import requests
from scipy.ndimage import gaussian_filter
import matplotlib.pyplot as plt
import geopandas as gpd
import osmnx as ox
from PIL import Image
import plotly.graph_objects as go


def _deg2num(lat_deg, lon_deg, zoom):
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = (lon_deg + 180.0) / 360.0 * n
    ytile = (1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n
    return xtile, ytile


def fetch_and_stitch_tiles(bbox, zoom=16, tile_server='https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', out_png='backend/map/data/texture.png', max_tiles=64):
    """Fetch map tiles for bbox and stitch into a single image saved to out_png.
    Uses OSM tile server by default. Limits tile count to avoid abuse.
    """
    west, south, east, north = bbox
    # convert bbox corners to fractional tile coordinates
    x_min_f, y_max_f = _deg2num(north, west, zoom)
    x_max_f, y_min_f = _deg2num(south, east, zoom)

    x_min = int(math.floor(x_min_f))
    x_max = int(math.floor(x_max_f))
    y_min = int(math.floor(y_min_f))
    y_max = int(math.floor(y_max_f))

    nx = x_max - x_min + 1
    ny = y_max - y_min + 1
    tiles_count = nx * ny
    if tiles_count > max_tiles:
        raise RuntimeError(f"Requested {tiles_count} tiles; exceeds max_tiles={max_tiles}")

    tile_size = 256
    out_w = nx * tile_size
    out_h = ny * tile_size

    canvas = Image.new('RGB', (out_w, out_h))
    session = requests.Session()
    session.headers.update({'User-Agent': 'hackathon-map/1.0 (+https://example)'})

    for ix, x in enumerate(range(x_min, x_max + 1)):
        for iy, y in enumerate(range(y_min, y_max + 1)):
            url = tile_server.format(z=zoom, x=x, y=y)
            try:
                r = session.get(url, timeout=10)
                r.raise_for_status()
                tile = Image.open(io.BytesIO(r.content)).convert('RGB')
            except Exception:
                # fallback blank tile
                tile = Image.new('RGB', (tile_size, tile_size), (240, 240, 240))
            canvas.paste(tile, (ix * tile_size, iy * tile_size))

    # compute pixel coords of bbox within global pixel space
    # global pixel coordinates at given zoom
    n = 2 ** zoom
    def lonlat_to_global_px(lon, lat):
        x = (lon + 180.0) / 360.0 * n * tile_size
        lat_rad = math.radians(lat)
        y = (1 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2 * n * tile_size
        return x, y

    px_min, py_max = lonlat_to_global_px(west, north)
    px_max, py_min = lonlat_to_global_px(east, south)

    origin_x = x_min * tile_size
    origin_y = y_min * tile_size
    left = int(px_min - origin_x)
    upper = int(py_min - origin_y)
    right = int(px_max - origin_x)
    lower = int(py_max - origin_y)

    # crop and save
    cropped = canvas.crop((left, upper, right, lower))
    cropped.save(out_png)
    return out_png


def render_texture_image(bbox, edges_path='backend/map/data/edges.geojson', out_png='backend/map/data/texture.png', zoom=18):
    """Primary entry: fetch and return stitched tile image for bbox.
    Falls back to the matplotlib renderer if tile fetching fails.
    """
    try:
        return fetch_and_stitch_tiles(bbox, zoom=zoom, out_png=out_png)
    except Exception:
        # fallback to previous matplotlib renderer for simple vector styling
        west, south, east, north = bbox
        edges = gpd.read_file(edges_path)
        fig, ax = plt.subplots(figsize=(8, 8), dpi=150)
        ax.set_xlim(west, east)
        ax.set_ylim(south, north)
        ax.axis('off')
        ax.set_facecolor('#f0f0f0')
        try:
            edges.plot(ax=ax, color='orange', linewidth=1)
        except Exception:
            pass
        fig.savefig(out_png, bbox_inches='tight', pad_inches=0)
        plt.close(fig)
        return out_png


def drape_and_export(srtm_path='backend/map/data/srtm.tif', texture_png='backend/map/data/texture.png', out_html='backend/map/data/roads_draped.html', downsample=200, flat=False):
    # read SRTM raster
    with rasterio.open(srtm_path) as src:
        arr = src.read(1)
        arr = np.where(arr == src.nodata, np.nan, arr)
        # get bounds and transform to lon/lat grid
        left, bottom, right, top = src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top
        # build coordinates
        height, width = arr.shape
        xs = np.linspace(left, right, width)
        ys = np.linspace(bottom, top, height)
        XX, YY = np.meshgrid(xs, ys)

    # prepare DEM: replace nodata with nan
    dem = arr.astype(float)
    dem[dem == src.nodata] = np.nan
    # fill small gaps with median
    med = np.nanmedian(dem)
    dem = np.where(np.isnan(dem), med, dem)
    # smooth to remove spikes
    dem = gaussian_filter(dem, sigma=1)
    # clamp to a reasonable range around median to remove outliers
    min_allowed = med - 200
    max_allowed = med + 200
    dem = np.clip(dem, min_allowed, max_allowed)
    # apply vertical scale to reduce exaggeration
    vertical_scale = 0.25
    dem = dem * vertical_scale

    # downsample for speed
    step_x = max(1, width // downsample)
    step_y = max(1, height // downsample)
    Z = dem[::step_y, ::step_x]
    Lon = XX[::step_y, ::step_x]
    Lat = YY[::step_y, ::step_x]

    # load texture and resize to match Z shape
    img = Image.open(texture_png).convert('RGB')
    img = img.resize((Z.shape[1], Z.shape[0]), Image.LANCZOS)

    # Quantize to 256 colors and build a colorscale so the surface can display RGB-like texture
    pal = img.convert('P', palette=Image.ADAPTIVE, colors=256)
    indices = np.array(pal)  # 2D array of palette indices
    palette = pal.getpalette()  # flat list [r,g,b, r,g,b, ...]
    colorscale = []
    for i in range(256):
        r = palette[i * 3]
        g = palette[i * 3 + 1]
        b = palette[i * 3 + 2]
        colorscale.append([i / 255.0, f'rgb({r},{g},{b})'])

    # If flat=True, render the surface at a constant elevation to show imagery without terrain bumps
    if flat:
        Zflat = np.zeros_like(Lon, dtype=float)
        fig = go.Figure(data=[go.Surface(z=Zflat.tolist(), x=Lon.tolist(), y=Lat.tolist(), surfacecolor=indices.tolist(), colorscale=colorscale, cmin=0, cmax=255, showscale=False)])
    else:
        fig = go.Figure(data=[go.Surface(z=Z.tolist(), x=Lon.tolist(), y=Lat.tolist(), surfacecolor=indices.tolist(), colorscale=colorscale, cmin=0, cmax=255, showscale=False)])

    # overlay road traces from graph.json (thin 3D lines)
    # NOTE: road overlays removed to show raw imagery. If you want road traces,
    # we can add them back as subtle lines (thin, dark) on request.

    fig.update_layout(scene=dict(xaxis_title='lon', yaxis_title='lat', zaxis_title='elevation (m)'), width=1200, height=900)
    fig.write_html(out_html)
    return out_html


def main():
    # determine bbox from existing graph
    G = ox.load_graphml('backend/map/data/graph.graphml')
    nodes, edges = ox.graph_to_gdfs(G)
    minx, miny, maxx, maxy = nodes.total_bounds
    bbox = (minx, miny, maxx, maxy)
    tex = render_texture_image(bbox, edges_path='backend/map/data/edges.geojson', out_png='backend/map/data/texture.png')
    out = drape_and_export(srtm_path='backend/map/data/srtm.tif', texture_png=tex, out_html='backend/map/data/roads_draped.html', downsample=250)
    print('Generated', out)


if __name__ == '__main__':
    main()
