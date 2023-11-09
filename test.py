import json
import requests


def readNetwork(path_name):
    with open(path_name, 'r') as readFile:
        return json.load(readFile)


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


def insert_data(id, port_in, port_out):
    with open("template.json", 'r') as readFile:
        template = json.load(readFile)
    template["deviceId"] = template['deviceId'].replace('x', '{:015X}'.format(id).lower())
    template['treatment']['instrucions'][0]['port'] = str(port_in)
    template['selector']['criteria'][0]['port'] = str(port_out)


def configure_switches(src,dst,network):
    flows = []
configure_switches()
network_graph = readNetwork('network.json')
source_node = 'h1'
target_node = 'h10'
starting_switch = list(network_graph['hosts'][source_node])[0]
ending_switch = list(network_graph['hosts'][target_node])[0]

weights = {"delay": 1.0, "bw": 0.0, "loss": 2.0}
# for additional parameter of link
# weights = {"delay": 1.0, "bw": 0.0, "loss": 2.0, "max_queue_size": 0.0}
path, value = bellman_ford(network_graph['switches'], starting_switch, ending_switch, weights)

if path:
    print(f"Najkrótsza ścieżka między {starting_switch} a {ending_switch}: {path}")
else:
    print(f"Brak ścieżki między {starting_switch} a {ending_switch}")
