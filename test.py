import json
import requests


def readNetwork(path_name):
    with open(path_name, 'r') as readFile:
        return json.load(readFile)


def shortestPath(src, dest):
    network = readNetwork('network.json')
    unvisited_nodes = [key for key in list(network.keys()) if key[0]=='s']
    ending_switch = list(network[dest].keys())[0]
    current_node = list(network[src].keys())[0]
    path = [current_node]
    while unvisited_nodes:
        unvisited_nodes.pop(unvisited_nodes.index(current_node))
        if len(network[current_node])==1:
            current_node = list(network[current_node].keys())[0]
        elif len(network[current_node])==2 and (list(network[current_node].keys())[0]!=dest or list(network[current_node].keys())[1]!=dest):
            current_node = list(network[current_node].keys())[0] if list(network[current_node].keys())[0][0]=='s' else list(network[current_node].keys())[1]
        else:
            current_node = min(set(network[current_node].keys()).intersection(unvisited_nodes), key=lambda node: float(network[current_node][node]['delay'][0:-2]) if float(network[current_node][node]['delay'][0:-2]) != 0.0 else float("inf"))
        if current_node == ending_switch:
            path.append(current_node)
            return path
        path.append(current_node)


# shortestPath("h1","h10")

def dijkstra(graph, start, end):
    # Initialize distances and predecessors
    distances = {}
    predecessors = {}
    for node in graph:
        if node[0] == 's':
            predecessors[node] = None
            distances[node] = float('inf')
    distances[start] = 0

    # Create a set of unvisited nodes
    unvisited_nodes = set(graph).intersection(set(distances.keys()))
    current_node = start
    while unvisited_nodes:
        # Select the node with the smallest non-zero delay
        current_node = min(unvisited_nodes.intersection(set(graph[current_node].keys())), key=lambda node: float(graph[current_node][node]['delay'][:-2]) if 'delay' in graph[current_node][node] and graph[current_node][node]['delay'] != '0ms' else float('inf'))

        # Stop if we reach the end node
        if current_node == end:
            path = []
            while current_node is not None:
                path.insert(0, current_node)
                current_node = predecessors[current_node]
            return path

        unvisited_nodes.remove(current_node)

        for neighbor, edge_attributes in graph[current_node].items():
            if 'delay' in edge_attributes and edge_attributes['delay'] != '0ms':
                weight = float(edge_attributes['delay'][:-2])
            else:
                weight = float('inf')

            alternative_route = distances[current_node] + weight
            if neighbor[0] != 'h':
                if alternative_route < distances[neighbor]:
                    distances[neighbor] = alternative_route
                    predecessors[neighbor] = current_node

    return None


def bellman_ford1(graph, src, dest):
    dist = {}
    prev = {}

    # Inicjalizacja odległości do wszystkich wierzchołków jako nieskończoność
    for switch in graph:
        dist[switch] = float('inf')
        prev[switch] = None

    dist[src] = 0

    for _ in range(len(graph) - 1):
        for switch in graph:
            for neighbor, edge_info in graph[switch].items():
                if dist[switch] + float(edge_info['delay'][:-2]) < dist[neighbor]:
                    dist[neighbor] = dist[switch] + float(edge_info['delay'][:-2])
                    prev[neighbor] = switch

    # Sprawdzenie czy istnieje cykl o ujemnej wadze
    for switch in graph:
        for neighbor, edge_info in graph[switch].items():
            if dist[switch] + float(edge_info['delay'][:-2]) < dist[neighbor]:
                print("Graf zawiera cykl o ujemnej wadze")
                return

    # Odtwarzanie najkrótszej ścieżki
    path = []
    current = dest
    while current is not None:
        path.insert(0, current)
        current = prev[current]

    return path, dist[dest]


def bellman_ford(graph, src, dest, weights):
    dist = {}
    prev = {}

    for switch in graph:
        dist[switch] = float('inf')
        prev[switch] = None

    dist[src] = 0

    for _ in range(len(graph) - 1):
        for switch in graph:
            for neighbor, edge_info in graph[switch].items():
                total_weight = 0
                for weight_name, weight_value in weights.items():
                    if weight_name == "delay":
                        total_weight += float(edge_info[weight_name][:-2]) * weight_value
                    else:
                        total_weight += float(edge_info[weight_name]) * weight_value

                if dist[switch] + total_weight < dist[neighbor]:
                    dist[neighbor] = dist[switch] + total_weight
                    prev[neighbor] = switch

    for switch in graph:
        for neighbor, edge_info in graph[switch].items():
            total_weight = 0
            for weight_name, weight_value in weights.items():
                if weight_name == "delay":
                    total_weight += float(edge_info[weight_name][:-2]) * weight_value
                else:
                    total_weight += float(edge_info[weight_name]) * weight_value

            if dist[switch] + total_weight < dist[neighbor]:
                print("Graf zawiera cykl o ujemnej wadze")
                return

    path = []
    current = dest
    while current is not None:
        path.insert(0, current)
        current = prev[current]

    return path, dist[dest]
network_graph = readNetwork('network.json')
source_node = 'h1'
target_node = 'h10'
starting_switch = list(network_graph['hosts'][source_node])[0]
ending_switch = list(network_graph['hosts'][target_node])[0]

weights = {"delay": 1.0, "bw": 0.0, "loss": 2.0}
path, value = bellman_ford(network_graph['switches'], starting_switch, ending_switch,weights)

if path:
    print(f"Najkrótsza ścieżka między {starting_switch} a {ending_switch}: {path}")
    print(f"Całkowita wartość parametrów: {value}")
else:
    print(f"Brak ścieżki między {starting_switch} a {ending_switch}")

