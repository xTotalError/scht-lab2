import asyncio
import json
from operator import itemgetter
from typing import Dict

import requests
from requests import Response


def read_json_file(file_path: str) -> Dict:
    try:
        with open(file_path, 'r') as read_file:
            data = json.load(read_file)
        return data
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return {}
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON in file '{file_path}': {e}")
        return {}


def insert_data(device_id: int, port_in: str, port_out: str, dst: int) -> [str]:
    template = read_json_file("template.json")
    template["deviceId"] = template['deviceId'].replace('x', '{:016X}'.format(device_id).lower())
    template['treatment']['instructions'][0]['port'] = str(port_in)
    template['selector']['criteria'][0]['port'] = str(port_out)
    template['selector']['criteria'][2]['ip'] = template['selector']['criteria'][2]['ip'].replace('y', str(dst))
    return template


def generate_config(ports: [str], path):
    flows = []

    # two-way connection from source host and switch directly linked
    def add_flow(src: int, src_port: str, dst_port: str, dst: int) -> None:
        flows.append(insert_data(src, src_port, dst_port, dst))

    for i, switch in enumerate(path):
        current_id = path[i]
        src_id = path[i - 1] if i > 0 else None
        dst_id = path[i + 1] if i < len(path) - 1 else None

        if src_id and dst_id:
            # center
            add_flow(int(current_id[1:]), ports[current_id][src_id], ports[current_id][dst_id], int(path[0][1:]))
            add_flow(int(current_id[1:]), ports[current_id][dst_id], ports[current_id][src_id], int(path[-1][1:]))
        elif dst_id:
            # beginning
            host_port = str(len(ports[current_id]) + 1)
            add_flow((int(current_id[1:])), host_port, ports[current_id][dst_id], int(path[0][1:]))
            add_flow((int(current_id[1:])), ports[current_id][dst_id], host_port, int(path[-1][1:]))
        elif src_id:
            # end
            host_port = str(len(ports[current_id]) + 1)
            add_flow((int(current_id[1:])), ports[current_id][src_id], host_port, int(path[0][1:]))
            add_flow((int(current_id[1:])), host_port, ports[current_id][src_id], int(path[-1][1:]))

    return {"flows": flows}


def request_changes(link, path) -> Response:
    header = {'Content-Type': 'application/json', "Accept": "application/json"}
    content = json.dumps(generate_config(link, path))
    url = "http://192.168.33.104:8181/onos/v1/flows"
    return requests.post(url, content, auth=('onos', 'rocks'), headers=header)


def find_paths_with_max_bw(graph, source, target, requested_bw=0):
    stack = [([source], float('inf'))]
    paths = []

    while stack:
        current_path, min_bw = stack.pop()

        current_node = current_path[-1]

        for neighbor, edge_info in graph[current_node].items():
            if neighbor not in current_path[:-1]:
                next_bw = min(min_bw, edge_info["bw"])

                if neighbor == target:
                    paths.append((current_path + [neighbor], next_bw))
                else:
                    stack.append((current_path + [neighbor], next_bw))

    max_bw = max(paths, key=lambda x: x[1])[1]
    if max_bw < requested_bw and max_bw != 0:
        paths_with_max_bw = [path for path, bw in paths if bw == max_bw]
    else:
        paths_with_max_bw = [path for path, bw in paths if max_bw >= bw >= requested_bw]
    return paths_with_max_bw


def get_path_with_lowest_number_of_connections(paths):
    min_path = len(paths[0])
    for i in range(1, len(paths)):
        if len(paths[i]) < min_path:
            min_path = len(paths[i])
    return [path for path in paths if len(path) <= min_path]


def calculate_delay(path, switches):
    delay = 0
    for i in range(len(path) - 1):
        delay += float(switches[path[i]][path[i + 1]]["delay"][:-2])
    return delay


def get_path_with_min_or_max_delay(paths, switches, desc, max_delay=float('inf')):
    result = []
    alt_result = []
    for path in paths:
        delay = calculate_delay(path, switches)
        if delay <= max_delay:
            result.append([path, delay])
        else:
            alt_result.append([path, delay])
    if result:
        print(sorted(result, key=itemgetter(1), reverse=desc)[0] if len(result) != 1 else result[0])
        return sorted(result, key=itemgetter(1), reverse=desc)[0][0] if len(result) != 1 else result[0][0]
    print(sorted(alt_result, key=itemgetter(1), reverse=desc)[0] if len(alt_result) != 1 else alt_result[0])
    return sorted(alt_result, key=itemgetter(1), reverse=desc)[0][0] if len(alt_result) != 1 else alt_result[0][0]


def check_if_paths_with_loss(paths, nodes):
    updated_path = []
    for path in paths:
        has_loss = False
        for i in range(len(path) - 1):
            if nodes[path[i]][path[i + 1]]['loss'] != 0:
                has_loss = True
        if not has_loss:
            updated_path.append(path)
    if updated_path:
        return updated_path
    else:
        return paths


def simulate_data_stream(nodes, hosts, file_name, flow_history):
    streams = read_json_file(file_name)
    links = read_json_file("ports.json")
    for item in streams:
        src = item['src']
        dst = item['dst']
        src_switch = list(hosts[src])[0]
        end_switch = list(hosts[dst])[0]
        protocol = item['protocol']
        if protocol == 'tcp':
            max_bw = item['max_bw']
            window = item['window']
            max_delay = (window * 8 * 1024 ** 2) / (2 * max_bw * 10 ** 6) if max_bw != 0 else 0
            paths_with_max_bw = find_paths_with_max_bw(nodes, src_switch, end_switch, max_bw)
            if paths_with_max_bw:
                path = get_path_with_min_or_max_delay(get_path_with_lowest_number_of_connections(
                    check_if_paths_with_loss(paths_with_max_bw, nodes)), nodes, True, max_delay)
            else:
                print(f"Connection({item}) Failed: Insufficient Bandwidth.")
                continue
            eff_bw = round(8 * window / (2 * calculate_delay(path, nodes)))
            # reduce bandwidth by the value used in connection
            if eff_bw <= max_bw:
                used_bw = eff_bw
                for i in range(0, len(path) - 1):
                    nodes[path[i]][path[i + 1]]['bw'] -= eff_bw
                    nodes[path[i + 1]][path[i]]['bw'] -= eff_bw
            else:
                used_bw = max_bw
                for i in range(0, len(path) - 1):
                    nodes[path[i]][path[i + 1]]['bw'] -= max_bw
                    nodes[path[i + 1]][path[i]]['bw'] -= max_bw
        elif protocol == 'udp':
            requested_bw = item["b_rate"] * item['b_size'] * 0.008
            paths_with_max_bw = find_paths_with_max_bw(nodes, src_switch, end_switch, requested_bw)
            if paths_with_max_bw:
                path = get_path_with_min_or_max_delay(check_if_paths_with_loss(
                    paths_with_max_bw, nodes), nodes, False)
            else:
                print(f"Connection({item}) Failed: Insufficient Bandwidth.")
                continue
            used_bw = requested_bw

            for i in range(0, len(path) - 1):
                if nodes[path[i]][path[i + 1]]['bw'] > requested_bw:
                    nodes[path[i]][path[i + 1]]['bw'] -= requested_bw
                    nodes[path[i + 1]][path[i]]['bw'] -= requested_bw
                else:
                    nodes[path[i]][path[i + 1]]['bw'] = 0
                    nodes[path[i + 1]][path[i]]['bw'] = 0
        else:
            return
        response = request_changes(links, path)
        device_id, flow_id = response.json()["flows"][0].values()
        flow_history.append([device_id, flow_id, used_bw, path])
    return flow_history, nodes


async def check_if_flow_still_lasts(device_id, flow_id):
    url = f"http://192.168.33.104:8181/onos/v1/flows/{device_id}/{flow_id}"
    resp = await loop.run_in_executor(None, lambda: requests.get(url=url, auth=('onos', 'rocks'),
                                                                 headers={"Accept": "application/json"}))

    if resp.status_code == 200:
        return resp.json().get("flows", {})
    else:
        # Handle HTTP error status codes
        print(f"Error: {resp.status_code}\n")
        print(f"Error: {resp.content}")
        return {}


def update_network(nodes, used_bw, path):
    for i in range(len(path) - 1):
        nodes[path[i]][path[i + 1]]["bw"] += used_bw
        nodes[path[i + 1]][path[i]]["bw"] += used_bw
    return nodes


async def check_flows_periodically(nodes, flow_history, interval_seconds=1):
    while flow_history:
        updated_flow_history = []
        for device_id, flow_id, used_bw, path in flow_history:
            flow_status = await check_if_flow_still_lasts(device_id, flow_id)
            if flow_status:
                # The flow is still active, keep it in the updated list
                updated_flow_history.append((device_id, flow_id, used_bw, path))
            else:
                nodes = update_network(nodes, used_bw, path)

        # Update the flow_history with the list of active flows
        flow_history[:] = updated_flow_history

        await asyncio.sleep(interval_seconds)
    return nodes


if __name__ == "__main__":
    network_graph = read_json_file('network.json')
    SWITCHES: [] = network_graph['switches']
    HOSTS: [] = network_graph['hosts']
    FILE_NAME = input("Enter path to file with connections to make or write 'exit' to stop: ")
    loop = asyncio.get_event_loop()
    FLOW_HISTORY = []
    while FILE_NAME != "exit":
        FLOW_HISTORY, SWITCHES = simulate_data_stream(SWITCHES, HOSTS, FILE_NAME, FLOW_HISTORY)
        SWITCHES = loop.run_until_complete(check_flows_periodically(SWITCHES, FLOW_HISTORY))
        FILE_NAME = input("Enter path to file with connections to make or write 'exit' to stop: ")
    loop.close()
