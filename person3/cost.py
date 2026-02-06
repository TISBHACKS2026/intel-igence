# file to find cost of each route, for a specific car
# networkx sees which route has lowest cost for a particular car, and then decides which route it will use


# finds the speed that the car will travel at in a flood of given depth
def compute_speed_in_flood(base_speed_kmph, flood_depth_m, loss_rate_per_mm):
    flood_depth_mm = flood_depth_m * 1000
    speed_loss = loss_rate_per_mm * flood_depth_mm
    adjusted_speed_kmph = max(base_speed_kmph - speed_loss, 0)
    return max(0.1, adjusted_speed_kmph)  

#finds time taken to travel a given edge length at a given speed
def compute_travel_time(edge_length_m, speed_kmph):
    speed_mps = speed_kmph * 5/18
    travel_time_s = edge_length_m/speed_mps 
    return travel_time_s

# finds the area of flooding on a given edge, which is used to calculate the penalty for that edge
def compute_flooding_exposure(flood_depth_m, edge_length_m):
    exposure = flood_depth_m * edge_length_m
    return exposure

def 
    
    


