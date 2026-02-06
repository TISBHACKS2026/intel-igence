import networkx as nx
from cost import compute_edge_weight
from car import get_vehicle_profile, create_vehicle, Cars
import random 
#computes route based on the graph, start and end nodes, and vehicle profile. It first computes edge weights using the cost function and then uses Dijkstra's algorithm to find the shortest path based on those weights.
def compute_route(g: nx.Graph, source_node: int, target_node: int, vehicle_profile: Cars) -> list:

