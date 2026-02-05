"""Create a textured 3D terrain by draping a matplotlib-rendered map image
over the SRTM terrain and roads.

Outputs: backend/map/data/roads_draped.html
"""
import os
import rasterio
import numpy as np
import matplotlib.pyplot as plt
import geopandas as gpd
import osmnx as ox
from PIL import Image
import plotly.graph_objects as go


def render_texture_image(bbox, edges_path='backend/map/data/edges.geojson', out_png='backend/map/data/texture.png', dpi=150, img_size=(800,800)):
    west, south, east, north = bbox
    # load edges
    edges = gpd.read_file(edges_path)

    # fetch water and buildings for visual richness (osmnx API varies by version)
    try:
        if hasattr(ox, 'geometries_from_bbox'):
            water = ox.geometries_from_bbox(north, south, east, west, tags={"natural": "water"})
            waterways = ox.geometries_from_bbox(north, south, east, west, tags={"waterway": "riverbank"})
            buildings = ox.geometries_from_bbox(north, south, east, west, tags={"building": True})
        else:
            # older osmnx: fall back to empty GeoDataFrames
            water = gpd.GeoDataFrame()
            waterways = gpd.GeoDataFrame()
            buildings = gpd.GeoDataFrame()
    except Exception:
        water = gpd.GeoDataFrame()
        waterways = gpd.GeoDataFrame()
        buildings = gpd.GeoDataFrame()

    fig, ax = plt.subplots(figsize=(img_size[0] / dpi, img_size[1] / dpi), dpi=dpi)
    ax.set_xlim(west, east)
    ax.set_ylim(south, north)
    ax.axis('off')

    # background
    ax.set_facecolor('#f0f0f0')

    if not water.empty:
        try:
            water.to_crs(epsg=4326).plot(ax=ax, color='#a6cee3', linewidth=0)
        except Exception:
            pass
    if not waterways.empty:
        try:
            waterways.to_crs(epsg=4326).plot(ax=ax, color='#a6cee3', linewidth=0)
        except Exception:
            pass
    if not buildings.empty:
        try:
            buildings.to_crs(epsg=4326).plot(ax=ax, color='#bdbdbd', linewidth=0)
        except Exception:
            pass

    # plot edges, color by highway if available
    if not edges.empty:
        try:
            # simple styling: major roads thicker and orange
            def style(edge):
                t = edge.get('highway')
                if isinstance(t, list):
                    t = t[0]
                if t in ('motorway', 'trunk', 'primary'):
                    return {'color': '#d95f02', 'linewidth': 2.5}
                if t in ('secondary', 'tertiary'):
                    return {'color': '#ffbf69', 'linewidth': 1.8}
                return {'color': '#fdbf6f', 'linewidth': 0.8}

            for _, row in edges.iterrows():
                geom = row.geometry
                props = style(row)
                if geom is None:
                    continue
                xs, ys = geom.xy
                ax.plot(xs, ys, color=props['color'], linewidth=props['linewidth'], solid_capstyle='round')
        except Exception:
            edges.plot(ax=ax, color='orange', linewidth=1)

    fig.savefig(out_png, bbox_inches='tight', pad_inches=0)
    plt.close(fig)
    return out_png


def drape_and_export(srtm_path='backend/map/data/srtm.tif', texture_png='backend/map/data/texture.png', out_html='backend/map/data/roads_draped.html', downsample=200):
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

    # downsample for speed
    step_x = max(1, width // downsample)
    step_y = max(1, height // downsample)
    Z = arr[::step_y, ::step_x]
    Lon = XX[::step_y, ::step_x]
    Lat = YY[::step_y, ::step_x]

    # load texture and resize to match Z shape
    img = Image.open(texture_png).convert('RGB')
    img = img.resize((Z.shape[1], Z.shape[0]), Image.LANCZOS)
    img_arr = np.asarray(img)

    # plotly surface expects z as 2D list, and surfacecolor can be an array
    fig = go.Figure(data=[go.Surface(z=Z.tolist(), x=Lon.tolist(), y=Lat.tolist(), surfacecolor=img_arr[:,:,0].tolist(), colorscale='Greys', showscale=False)])

    # overlay road traces from graph.json (thin 3D lines)
    try:
        import json
        from networkx.readwrite import json_graph
        with open('backend/map/data/graph.json') as f:
            data = json.load(f)
        G = json_graph.node_link_graph(data)
        count = 0
        for u,v,k,d in G.edges(keys=True,data=True):
            # downsample trace plotting
            if count % 20 != 0:
                count += 1
                continue
            geom = d.get('geometry')
            if geom and isinstance(geom, dict):
                coords = geom.get('coordinates', [])
            else:
                nu = G.nodes[u]; nv = G.nodes[v]
                coords = [(nu['x'], nu['y']), (nv['x'], nv['y'])]
            elev = d.get('avg_elevation') or 0
            xs = [c[0] for c in coords]; ys=[c[1] for c in coords]; zs=[elev]*len(xs)
            fig.add_trace(go.Scatter3d(x=xs, y=ys, z=zs, mode='lines', line=dict(width=3,color='orange')))
            count += 1
    except Exception:
        pass

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
