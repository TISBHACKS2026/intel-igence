import json
from networkx.readwrite import json_graph
import plotly.graph_objects as go

def main():
    with open('backend/map/data/graph.json') as f:
        data = json.load(f)
    G = json_graph.node_link_graph(data)

    fig = go.Figure()
    count = 0
    for u,v,k,d in G.edges(keys=True,data=True):
        # downsample: plot 1/10 edges for quick preview
        if count % 10 != 0:
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
        fig.add_trace(go.Scatter3d(x=xs, y=ys, z=zs, mode='lines', line=dict(width=2,color='brown')))
        count += 1

    fig.update_layout(scene=dict(xaxis_title='lon', yaxis_title='lat', zaxis_title='elevation (m)'), width=1200, height=800)
    fig.write_html('backend/map/data/roads_3d.html')
    print('wrote backend/map/data/roads_3d.html')

if __name__ == '__main__':
    main()
