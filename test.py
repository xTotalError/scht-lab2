import asyncio
import json
from operator import itemgetter
from typing import Dict, Tuple

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

    max_bw = max(paths, key=lambda x: x[1], default=(None, 0))[1]
    if max_bw < requested_bw:
        paths_with_max_bw = [path for path, bw in paths if bw == max_bw]
    elif requested_bw != 0:
        paths_with_max_bw = [path for path, bw in paths if max_bw >= bw >= requested_bw]
    else:
        paths_with_max_bw = [path for path, bw in paths if max_bw >= bw > requested_bw]
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


def get_new_flows(path, flow_id) -> Tuple[str, Dict]:
    url = "http://192.168.33.104:8181/onos/v1/flows/of:" + '{:016X}'.format(int(path[0][1:], 16)).lower() + flow_id
    resp = requests.get(url=url, auth=('onos', 'rocks'), headers={"Accept": "application/json"})

    if resp.status_code == 200:
        return resp.url, resp.json().get("flows", {})
    else:
        # Handle HTTP error status codes
        print(f"Error: {resp.status_code}\n")
        print(f"Error: {resp.content}")
        return resp.url, {}


def simulate_data_stream(nodes, hosts):
    streams = read_json_file("streams.json")
    links = read_json_file("ports.json")
    flow_history = []
    used_bw = 0
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
            path = get_path_with_min_or_max_delay(get_path_with_lowest_number_of_connections(
                find_paths_with_max_bw(nodes, src_switch, end_switch, max_bw)), nodes, True, max_delay)
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
            path = get_path_with_min_or_max_delay(
                find_paths_with_max_bw(nodes, src_switch, end_switch, requested_bw), nodes, False)
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
        flow_history.append([device_id, flow_id, used_bw])
    loop.run_until_complete(check_flows_periodically(flow_history))
    loop.close()


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


async def check_flows_periodically(flow_history, interval_seconds=60):
    while True:
        updated_flow_history = []
        for device_id, flow_id, used_bw in flow_history:
            flow_status = await check_if_flow_still_lasts(device_id, flow_id)['flows']
            if flow_status:
                # The flow is still active, keep it in the updated list
                updated_flow_history.append((device_id, flow_id, used_bw))
            else:
                print(f'Flow with id:{flow_id} from device with id:{device_id} has ended.')

        # Update the flow_history with the list of active flows
        flow_history[:] = updated_flow_history

        await asyncio.sleep(interval_seconds)



if __name__ == "__main__":
    network_graph = read_json_file('network.json')
    SWITCHES: [] = network_graph['switches']
    HOSTS: [] = network_graph['hosts']
    simulate_data_stream(SWITCHES, HOSTS)
    loop = asyncio.get_event_loop()
