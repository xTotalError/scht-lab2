import json
import requests
from operator import itemgetter
import networkx as nx


def readNetwork(path_name):
    with open(path_name, 'r') as readFile:
        return json.load(readFile)


def bellman_ford(graph, src, dest, weigh):
    dist = {}
    prev = {}

    for switch in graph:
        dist[switch] = float('inf')
        prev[switch] = None

    dist[src] = 0

    for _ in range(len(graph) - 1):
        for switch in graph:
            for neighbor, edge_info in graph[switch].items():
                # Calculate total weight considering bandwidth
                total_weight = 0
                for weight_name, weight_value in weigh.items():
                    if weight_name == "delay":
                        total_weight += float(edge_info[weight_name][:-2]) * weight_value
                    else:
                        total_weight += float(edge_info[weight_name]) * weight_value

                # Update distance and bandwidth if a shorter path is found
                if dist[switch] + total_weight < dist[neighbor]:
                    dist[neighbor] = dist[switch] + total_weight
                    prev[neighbor] = switch

    for switch in graph:
        for neighbor, edge_info in graph[switch].items():
            # Calculate total weight considering bandwidth
            total_weight = 0
            for weight_name, weight_value in weigh.items():
                if weight_name == "delay":
                    total_weight += float(edge_info[weight_name][:-2]) * weight_value
                else:
                    total_weight += float(edge_info[weight_name]) * weight_value

            # Check for negative weight cycle
            if dist[switch] + total_weight < dist[neighbor]:
                print("Graph contains a negative weight cycle")
                return

    # Reconstruct the path
    path = []
    current = dest
    while current is not None:
        path.insert(0, current)
        current = prev[current]

    return path


def insert_data(device_id, port_in, port_out, dst):
    with open("template.json", 'r') as readFile:
        template = json.load(readFile)
    template["deviceId"] = template['deviceId'].replace('x', '{:016X}'.format(device_id).lower())
    template['treatment']['instructions'][0]['port'] = str(port_in)
    template['selector']['criteria'][0]['port'] = str(port_out)
    template['selector']['criteria'][2]['ip'] = template['selector']['criteria'][2]['ip'].replace('y',dst[1:])
    return template


def generate_config(ports, path):
    flows = []
    # two-way connection from source host and switch directly linked
    for i in range(0,len(path)):
        if i == 0:
            src = path[i]
            dst = path[i+1]
            flows.append(insert_data(int(src[1:]), len(ports[src]) + 1, ports[src][dst], path[0]))
            flows.append(insert_data(int(src[1:]), ports[src][dst], len(ports[src]) + 1, path[len(path)-1]))
        elif i == len(path)-1:
            src = path[i]
            dst = path[i-1]
            flows.append(insert_data(int(src[1:]), ports[src][dst], len(ports[src]) + 1, path[0]))
            flows.append(insert_data(int(src[1:]), len(ports[src])+1, ports[src][dst], path[len(path)-1]))
        else:
            src = path[i-1]
            curr = path[i]
            dst = path[i+1]
            flows.append(insert_data(int(curr[1:]), ports[curr][src], ports[curr][dst], path[0]))
            flows.append(insert_data(int(curr[1:]), ports[curr][dst], ports[curr][src], path[len(path)-1]))
    return {"flows": flows}


def request_changes(link, path):
    header = {'Content-Type': 'application/json', "Accept": "application/json"}
    content = json.dumps(generate_config(link, path))
    requests.post("http://192.168.33.104:8181/onos/v1/flows", content, auth=('onos', 'rocks'), headers=header)


def find_paths_with_max_bw(graph, source, target, protocol, requested_bw=0):
    stack = [(source, [(source, None)], float('inf'))]
    paths = []

    while stack:
        current_node, current_path, min_bw = stack.pop()

        for neighbor, edge_info in graph[current_node].items():
            if neighbor not in [node for node, _ in current_path]:
                next_bw = min(min_bw, edge_info["bw"])

                if neighbor == target:
                    paths.append((current_path + [(neighbor, None)], next_bw))
                else:
                    stack.append((neighbor, current_path + [(neighbor, None)], next_bw))

    max_bw = max(paths, key=lambda x: x[1], default=(None, 0))[1]
    if max_bw < requested_bw:
        paths_with_max_bw = [path for path, bw in paths if bw == max_bw]
    elif requested_bw != 0:
        paths_with_max_bw = [path for path, bw in paths if max_bw >= bw >= requested_bw]
    else:
        paths_with_max_bw = [path for path, bw in paths if max_bw >= bw > requested_bw]
    for i in range(len(paths_with_max_bw)):
        for j in range(len(paths_with_max_bw[i])):
            paths_with_max_bw[i][j] = paths_with_max_bw[i][j][0]

    return paths_with_max_bw


def calculate_delay(path, switches):
    delay = 0
    for i in range(len(path)-1):
        delay += float(switches[path[i]][path[i+1]]["delay"][:-2])
    return delay


def get_path_with_minmax_delay(paths, switches, desc, max_delay=float('inf')):
    result = []
    alt_result = []
    for path in paths:
        delay = calculate_delay(path, switches)
        if delay <= max_delay:
            result.append([path,delay])
        else:
            alt_result.append([path, delay])
    if result:
        print(sorted(result, key=itemgetter(1), reverse=desc)[0] if len(result) != 1 else result[0])
        return sorted(result, key=itemgetter(1), reverse=desc)[0][0] if len(result) != 1 else result[0][0]
    print(sorted(alt_result, key=itemgetter(1), reverse=desc)[0] if len(alt_result) != 1 else alt_result[0])
    return sorted(alt_result, key=itemgetter(1), reverse=desc)[0][0] if len(alt_result) != 1 else alt_result[0][0]



def find_all_paths(graph, start, end):
    stack = [(start, [start])]
    paths = []

    while stack:
        (node, path) = stack.pop()
        for next_node in set(graph[node]) - set(path):
            new_path = path + [next_node]
            stack.append((next_node, new_path))
            if next_node == end:
                paths.append(new_path)

    return paths


def simulate_data_stream(nodes, hosts):
    with open("streams.json", 'r') as read_file:
        streams = json.load(read_file)
    with open("ports.json", 'r') as readFile:
        links = json.load(readFile)
    for item in streams:
        src = item['src']
        dst = item['dst']
        G = nx.DiGraph()
        # Add nodes and edges to the graph
        for source, destinations in nodes.items():
            for dest, values in destinations.items():
                delay = float(values["delay"].replace("ms", ""))
                G.add_edge(source, dest, delay=delay)
        src_switch = list(hosts[src])[0]
        end_switch = list(hosts[dst])[0]
        protocol = item['protocol']
        if protocol == 'tcp':
            max_delay = (item['window'] * 8 * 1024 ** 2) / (2*item['max_bw'] * 10 ** 6) if item['max_bw'] != 0 else 0
            path = get_path_with_minmax_delay(find_paths_with_max_bw(nodes, src_switch, end_switch, 'tcp'), nodes, False, max_delay)

            bottleneck = 0
            for i in range(0, len(path) - 1):
                if i == 0:
                    bottleneck = nodes[path[i]][path[i + 1]]['bw']
                else:
                    bottleneck = min(bottleneck, nodes[path[i]][path[i + 1]]['bw'])
            # reduce bandwidth by the value used in connection
            for i in range(0, len(path) - 1):
                nodes[path[i]][path[i + 1]]['bw'] -= item['max_bw']
                nodes[path[i + 1]][path[i]]['bw'] -= item['max_bw']
                nodes[path[i]][path[i + 1]]['used_protocol'] = 'tcp'
                nodes[path[i + 1]][path[i]]['used_protocol'] = 'tcp'
        elif protocol == 'udp':
            requested_bw = item["b_rate"] * item['b_size'] * 0.008
            path = get_path_with_minmax_delay(find_paths_with_max_bw(nodes, src_switch, end_switch,'udp', requested_bw), nodes,False)
            for i in range(0,len(path)-1):
                if nodes[path[i]][path[i+1]]['bw'] > requested_bw:
                    nodes[path[i]][path[i + 1]]['bw'] -= requested_bw
                    nodes[path[i + 1]][path[i]]['bw'] -= requested_bw
                else:
                    nodes[path[i]][path[i + 1]]['bw'] = 0
                    nodes[path[i + 1]][path[i]]['bw'] = 0
                nodes[path[i]][path[i + 1]]['used_protocol'] = 'udp'
                nodes[path[i + 1]][path[i]]['used_protocol'] = 'udp'
        request_changes(links, path)
    print('x')


if __name__ == "__main__":
    network_graph = readNetwork('network.json')
    switch = network_graph['switches']
    HOSTS = network_graph['hosts']
    simulate_data_stream(switch, HOSTS)



