import os
import re
from collections import defaultdict

def load_adl(file_name):
    # Specify the path to the ADL folder
    folder_path = 'ADL'  # Replace with your actual folder path

# List to store the contents of all ADL files
    adl_texts = {}

# Iterate over all files in the folder
    for filename in os.listdir(folder_path):
        if filename.endswith('.adl'):
            file_path = os.path.join(folder_path, filename)
            with open(file_path, 'r', encoding='utf-8') as file:
                adl_text = file.read()
                adl_texts[filename] = adl_text  # Store with filename as key
    return adl_texts[f'{file_name}.adl']
    
def extract_connector_order(adl_text):
    # Regex pattern to extract connectors and their roles
    connector_pattern = r'connector\s+(\w+)\s*{([^}]*)}'
    role_pattern = r'role\s+(\w+)\(?(\w*)\)?\s*=\s*([^;]+);'

    # Find all connectors
    connectors = re.findall(connector_pattern, adl_text)

    connector_order = []

    for connector_name, connector_body in connectors:
        roles = re.findall(role_pattern, connector_body)

        # Step 1: Identify the output role (has parameter j)
        output_role = None
        role_behaviors = {}

        for role_name, param, behavior in roles:
            role_behaviors[role_name] = behavior
            if param == 'j':
                output_role = role_name

        # If no output role is found, skip
        if not output_role:
            connector_order.append([connector_name, None, None, None])
            continue

        # Step 2: Follow the event flow from the output role
        behavior_sequence = role_behaviors[output_role]
        tokens = [token.strip() for token in behavior_sequence.split('->')]

        first_input_role = None
        second_input_role = None

        # Find all !j events
        exclamation_events = [t.replace('!j', '') for t in tokens if '!j' in t]

        # Traverse events to identify input roles
        for event in exclamation_events:
            for role_name, behavior in role_behaviors.items():
                if f"{event}?j" in behavior:
                    if not first_input_role:
                        first_input_role = role_name
                    elif not second_input_role and role_name != first_input_role:
                        second_input_role = role_name

        # Append the connector order
        connector_order.append([connector_name, output_role, first_input_role, second_input_role])

    return connector_order

# Parse the ADL to extract attachments and connector types
def parse_adl(adl_text):
    attachments = []
    connectors = {}
    
    # Parse connectors
    connector_pattern = r'declare (\w+) = (\w+);'

    for match in re.finditer(connector_pattern, adl_text):
        connector_wire = match.group(1)
        connector_type = match.group(2)
        connectors[connector_wire] = connector_type

    # Parse attachments
    attachment_pattern = r'attach ([\w.]+)\(\) = (.+);'
    for match in re.finditer(attachment_pattern, adl_text):
        component_port = match.group(1)
        roles = [role.strip() for role in match.group(2).split('<*>')]
        for role in roles:
            role_clean = role.split('(')[0]
            attachments.append((component_port, role_clean))

    return connectors, attachments


def build_graph(connectors, attachments, connector_order_list):
    # Build a lookup for connector order: map connector type to its chain of roles.
    # For example, for CSConnector: chain = [ "requester", "responder" ]
    conn_order = {}
    for entry in connector_order_list:
        ctype, out_role, in1, in2 = entry
        chain = [out_role]
        if in1:
            chain.append(in1)
        if in2:
            chain.append(in2)
        conn_order[ctype] = chain

    # Group attachments by connector instance and role.
    # Each attachment is a tuple: (component_port, "instance.role(...)" ).
    inst_roles = defaultdict(lambda: defaultdict(list))
    for comp, att in attachments:
        parts = att.split('.', 1)
        if len(parts) != 2:
            continue
        instance, role_part = parts
        role = role_part.split('(')[0]  # remove any parameters
        inst_roles[instance][role].append(comp)

    # Build the full graph.
    graph = defaultdict(list)
    
    # Process each connector instance.
    for inst, roles in inst_roles.items():
        if inst not in connectors:
            continue
        ctype = connectors[inst]
        if ctype not in conn_order:
            continue
        chain = conn_order[ctype]
        
        if len(chain) == 2:
            # Two-role chain: [output_role, final_role]
            out_role, final_role = chain
            if out_role in roles and final_role in roles:
                for src in roles[out_role]:
                    for tgt in roles[final_role]:
                        graph[src].append(tgt)
                # Add self–edge for each target.
                for tgt in roles[final_role]:
                    graph[tgt].append(tgt)
                    
        elif len(chain) == 3:
            # Three-role chain: [output_role, mid_role, final_role]
            out_role, mid_role, final_role = chain
            if out_role in roles and mid_role in roles:
                # Edge: output -> mid
                for src in roles[out_role]:
                    for mid in roles[mid_role]:
                        graph[src].append(mid)
            if final_role in roles:
                # Edge: mid -> final (if mid exists)
                if mid_role in roles:
                    for mid in roles[mid_role]:
                        for tgt in roles[final_role]:
                            graph[mid].append(tgt)
                # Direct edge: output -> final
                if out_role in roles:
                    for src in roles[out_role]:
                        for tgt in roles[final_role]:
                            graph[src].append(tgt)
                # Add self–edge for each final target.
                for tgt in roles[final_role]:
                    graph[tgt].append(tgt)
    
    # Remove duplicate targets.
    for node in graph:
        graph[node] = list(set(graph[node]))
    
    # Compute set of non-final ports.
    # For each connector instance, determine the final role from its chain.
    # Then add all ports attached to roles that are not final.
    non_final_ports = set()
    for inst, roles in inst_roles.items():
        if inst not in connectors:
            continue
        ctype = connectors[inst]
        if ctype not in conn_order:
            continue
        chain = conn_order[ctype]
        final_role = chain[-1]
        for role, comps in roles.items():
            if role != final_role:
                non_final_ports.update(comps)
    
    # Prune the graph: include only keys that appear in non_final_ports.
    pruned_graph = {}
    for node, targets in graph.items():
        if node in non_final_ports:
            pruned_graph[node] = targets
    # Also, if a port in non_final_ports didn't get any outgoing edge, add it with empty list.
    for port in non_final_ports:
        if port not in pruned_graph:
            pruned_graph[port] = []
    
    # print("Graph",pruned_graph)
    return pruned_graph


def strict_ordered_attachment_with_connector(adl_text: str, connector_order_list: list) -> dict:
    # Build a lookup for connector order.
    connector_order = {}
    for entry in connector_order_list:
        ctype, out_role, in1, in2 = entry
        inputs = []
        if in1 is not None:
            inputs.append(in1)
        if in2 is not None:
            inputs.append(in2)
        connector_order[ctype] = {'output': out_role, 'inputs': inputs}
    
    # Extract the system block (assumes "system <name> { ... }")
    system_match = re.search(r'system\s+\w+\s*\{(.*?)\n\}', adl_text, re.DOTALL)
    system_text = system_match.group(1) if system_match else ""
    
    # Parse "declare" statements to map each connector instance to its connector type.
    # e.g., "declare loginwire = CSConnector;"
    declare_pattern = r'declare\s+(\w+)\s*=\s*(\w+)\s*;'
    declares = re.findall(declare_pattern, system_text)
    connector_instances = {inst: ctype for inst, ctype in declares}
    
    # Parse "attach" statements.
    # Each attach statement is assumed to be of the form:
    #   attach Component.port() = connectorInstance.role(optional params) [<*> connectorInstance.role(optional) ...];
    attach_pattern = r'attach\s+([\w\.]+)\s*\(\)\s*=\s*(.+?);'
    attach_matches = re.findall(attach_pattern, system_text)
    
    # For each connector instance we record the LHS (component port) attached under each role.
    connector_usage = defaultdict(lambda: defaultdict(list))
    for lhs, rhs in attach_matches:
        parts = [part.strip() for part in rhs.split("<*>")]
        for part in parts:
            m = re.search(r'(\w+)\.(\w+)\s*\(', part)
            if m:
                instance, role = m.groups()
                connector_usage[instance][role].append(lhs)
    
    # Build immediate edges based on each connector instance.
    # For a connector of type T, data flows from every port attached on its output role
    # to every port attached on its input role(s).
    immediate_edges = defaultdict(list)
    for instance, roles in connector_usage.items():
        if instance not in connector_instances:
            continue
        ctype = connector_instances[instance]
        if ctype not in connector_order:
            continue
        out_role = connector_order[ctype]['output']
        input_roles = connector_order[ctype]['inputs']
        sources = roles.get(out_role, [])
        for in_role in input_roles:
            dests = roles.get(in_role, [])
            for s in sources:
                for d in dests:
                    immediate_edges[s].append(d)
    
    # Return the immediate mapping (each key maps only to its next-level downstream ports)
    #print("immediate_edges", immediate_edges)
    return dict(immediate_edges)

def merge_paths_with_strict_order(paths, attachment_order):
    merged_paths = []
    path_map = {tuple(path): path for path in paths}

    # Build a quick lookup for paths by their nodes
    node_to_paths = {}
    for path in paths:
        for node in path:
            if node not in node_to_paths:
                node_to_paths[node] = []
            node_to_paths[node].append(path)

    # Merge based on strict attachment order
    for path in paths:
        merged_path = []
        visited = set()

        for idx, node in enumerate(path):
            if node not in visited:
                merged_path.append(node)
                visited.add(node)

            # If node has defined attachments, follow them in the correct order
            if node in attachment_order:
                # Attach nodes in the exact order from the attachment_order
                for ordered_node in attachment_order[node]:
                    if ordered_node in visited:
                        continue  # Skip if already visited

                    # Recursively expand ordered nodes
                    stack = [ordered_node]
                    while stack:
                        current = stack.pop()
                        if current not in visited:
                            merged_path.append(current)
                            visited.add(current)

                            # Add any further attachments for this node
                            if current in attachment_order:
                                # Reverse to maintain order when using stack
                                stack.extend(reversed(attachment_order[current]))

        # Avoid duplicate merged paths
        if merged_path not in merged_paths:
            merged_paths.append(merged_path)

    return merged_paths

def enhanced_find_all_paths(graph, extracted_attachments):
    def dfs(current, path, all_paths):
        # Add current node to the path
        path.append(current)

        # If current node has no outgoing edges, it's an endpoint
        if current not in graph or not graph[current]:
            all_paths.append(list(path))
        else:
            for neighbor in graph[current]:
                if neighbor not in path:  # Avoid cycles
                    dfs(neighbor, path, all_paths)

        # Backtrack to explore other paths
        path.pop()

    def is_subsequence(sub, full):
        """Check if 'sub' is a subsequence of 'full'."""
        if len(sub) > len(full):
            return False
        it = iter(full)
        return all(node in it for node in sub)

    # Step 1: Run DFS to find all paths
    all_paths = []
    for start in graph.keys():
        dfs(start, [], all_paths)

    # Step 2: Remove duplicate paths
    unique_paths = []
    seen = set()
    for path in all_paths:
        path_str = " -> ".join(path)
        if path_str not in seen:
            seen.add(path_str)
            unique_paths.append(path)
    # Step 3: Remove redundant subpaths (subsequence-based)
    non_redundant_paths = []
    for idx, path in enumerate(unique_paths):
        is_subpath = False
        for jdx, other_path in enumerate(unique_paths):
            if idx != jdx and is_subsequence(path, other_path):
                is_subpath = True
                break
        if not is_subpath:
            non_redundant_paths.append(path)
    #print(non_redundant_paths)
    final_paths = merge_paths_with_strict_order(non_redundant_paths, extracted_attachments)
    return final_paths

def preprocess(file_name):
    # Main processing
    input_adl = load_adl(file_name)
    connectors, attachments = parse_adl(input_adl)
    connector_order = extract_connector_order(input_adl)
    graph = build_graph(connectors, attachments, connector_order)
    attachment_order = strict_ordered_attachment_with_connector(input_adl, connector_order)
    all_paths = enhanced_find_all_paths(graph, attachment_order) 
    return all_paths

def preprocess_with_adl(input_adl):
    # Main processing
    connectors, attachments = parse_adl(input_adl)
    connector_order = extract_connector_order(input_adl)
    graph = build_graph(connectors, attachments, connector_order)
    attachment_order = strict_ordered_attachment_with_connector(input_adl, connector_order)
    all_paths = enhanced_find_all_paths(graph, attachment_order)
    return all_paths

# --------------------------------------------------------------------------------#
# Get information of connector roles into the path
def get_system_block(adl_text):
    system_pattern = r"system\s+\w+\s*{([^}]+)}"
    system_block_match = re.search(system_pattern, adl_text, re.DOTALL)
    if system_block_match:
        system_block = system_block_match.group(1)
    else:
        system_block = ""
    return system_block

def get_declarations(system_block):
    # Find the system block.
    declare_pattern = r"declare\s+(\w+)\s*=\s*(\w+)\s*;"
    declarations = {}
    for decl_match in re.finditer(declare_pattern, system_block):
        var = decl_match.group(1)
        conn_type = decl_match.group(2)
        declarations[var] = conn_type
    return declarations

def get_attachments_lib(system_block):
    attach_pattern = r"attach\s+([\w\.]+\(\))\s*=\s*(.+?);"
    attachments = {}
    for attach_match in re.finditer(attach_pattern, system_block):
        comp_port_with_paren = attach_match.group(1)  # e.g., PassengerUI.call()
        # Remove trailing () to get just "PassengerUI.call"
        comp_port = comp_port_with_paren[:-2]
        rhs = attach_match.group(2).strip()
        # Split on the <*> separator if there are multiple segments
        segments = re.split(r"<\*>", rhs)
        attach_list = []
        seg_pattern = r"(\w+)\.(\w+)\s*\(.*?\)"
        for seg in segments:
            seg = seg.strip()
            seg_match = re.search(seg_pattern, seg)
            if seg_match:
                conn_var = seg_match.group(1)
                role = seg_match.group(2)
                attach_list.append((conn_var, role))
        attachments[comp_port] = attach_list
    return attachments

def get_attachments(comp_port, attachments):
    """Return the list of (connector, role) for the given component.port."""
    return attachments.get(comp_port.strip(), [])

def find_common_connector(compA, compB, attachments):
    attA = get_attachments(compA, attachments)
    attB = get_attachments(compB, attachments)
    for (conn, roleA) in attA:
        for (connB, roleB) in attB:
            if conn == connB:
                return conn, roleA, roleB
    return None

def compute_compound_fallbacks(nodes, attachments, declarations, connector_order):
    fb_dict = {}
    for i, node in enumerate(nodes):
        atts = get_attachments(node, attachments)
        if len(atts) > 1:
            used = set()
            # Check with previous node
            if i - 1 >= 0:
                common = find_common_connector(nodes[i-1], node, attachments)
                if common:
                    used.add(common[0])
            # Check with next node
            if i + 1 < len(nodes):
                common = find_common_connector(node, nodes[i+1], attachments)
                if common:
                    used.add(common[0])
            fb = {}
            for (conn, role) in atts:
                if conn in used:
                    continue
                conn_type = declarations.get(conn)
                if conn_type and conn_type in connector_order:
                    order = connector_order[conn_type]
                    try:
                        idx = order.index(role)
                        partner_role = order[idx + 1]
                        fb[conn] = (role, partner_role)
                    except (ValueError, IndexError):
                        pass
            if fb:
                fb_dict[i] = fb
    return fb_dict

def extend_path_with_connectorsinfo(path, connector_order, attachments, declarations):
    connector_order = {
        entry[0]: tuple(role for role in entry[1:] if role is not None)
        for entry in connector_order
    }

    nodes = [n.strip() for n in path]
    extended = [nodes[0]]
    compound_fallbacks = compute_compound_fallbacks(nodes, attachments, declarations, connector_order)
    last_conn = None
    last_trailing_role = None
    i = 0
    while i < len(nodes) - 1:
        compA = nodes[i]
        compB = nodes[i+1]
        common = find_common_connector(compA, compB, attachments)
        if common:
            conn, roleA, roleB = common
            # If same connector as previous and the left role equals the previous trailing role, skip it.
            if last_conn == conn and last_trailing_role == roleA:
                seg = f"{conn}.{roleB}"
            else:
                seg = f"{conn}.{roleA} -> {conn}.{roleB}"
            extended.append(seg)
            extended.append(compB)
            last_conn = conn
            last_trailing_role = roleB
            i += 1
        else:
            # No direct connector; try fallback from a previous compound node.
            fallback_used = False
            for j in range(i, -1, -1):
                if j in compound_fallbacks:
                    fb = compound_fallbacks[j]
                    for conn, (role, partner_role) in list(fb.items()):
                        # Check if compB has an attachment with this connector and expected partner_role.
                        for (c, r) in get_attachments(compB, attachments):
                            if c == conn and r == partner_role:
                                # Avoid duplicating the role if already the trailing role.
                                if last_conn == conn and last_trailing_role == role:
                                    seg = f"{conn}.{partner_role}"
                                else:
                                    seg = f"{conn}.{role} -> {conn}.{partner_role}"
                                extended.append(seg)
                                extended.append(compB)
                                last_conn = conn
                                last_trailing_role = partner_role
                                fallback_used = True
                                # Mark fallback branch as used.
                                del fb[conn]
                                break
                        if fallback_used:
                            break
                if fallback_used:
                    break
            if not fallback_used:
                extended.append(compB)
            i += 1
    return " -> ".join(extended)

def get_extended_paths_with_connector_info(file_name):
    input_adl = load_adl(file_name)
    declarations = get_declarations(get_system_block(input_adl))
    attachments = get_attachments_lib(get_system_block(input_adl))
    connector_order = extract_connector_order(input_adl)
    input_paths = preprocess(file_name)
    
    formatted_paths = ""
    for idx, path in enumerate(input_paths, start=1):
         result = extend_path_with_connectorsinfo(path, connector_order, attachments, declarations)
         formatted_paths += f"Path {idx}: {result}\n"
         
    return formatted_paths

# identify the assert statements from path
def identify_liveness_assert(file_name):
    input_adl = load_adl(file_name)
    paths = preprocess_with_adl(input_adl)
    """Extract the system name from the ADL text."""
    match = re.search(r'system\s+(\w+)\s*{', input_adl)
    system_name = match.group(1)

    """Extract component ports and their corresponding events."""
    pattern = r'component\s+(\w+)\s*{\s*(.*?)\s*}'
    components = {}
    for comp_match in re.finditer(pattern, input_adl, re.DOTALL | re.MULTILINE):
        component = comp_match.group(1)
        body = comp_match.group(2)
        ports = re.findall(r'port\s+(\w+)\s*\(\)\s*=\s*(\w+)\s*->\s*(\w+)\s*\(\)\s*;', body)
        for port_name, event, port in ports:
            components[f"{component}.{port_name}"] = event
    component_ports = components

    """Generate the assertion based on the given path and ADL."""
    assertions = []
    # Display all paths
    for path in paths: 
        initial_port = path[0]
        final_port = path[-1]
        # Find corresponding events
        initial_event = component_ports.get(initial_port, "unknown_event")
        final_event = component_ports.get(final_port, "unknown_event")
        # Generate the assertion
        assertion = f"assert {system_name} |= [] ({initial_port}.{initial_event} -> <> {final_port}.{final_event})"
        assertions.append(assertion)
    return assertions

def identify_liveness_assert_with_adl(input_adl):
    paths = preprocess_with_adl(input_adl)
    """Extract the system name from the ADL text."""

    match = re.search(r'system\s+(\w+)\s*{', input_adl)
    system_name = match.group(1)

    """Extract component ports and their corresponding events."""
    pattern = r'component\s+(\w+)\s*{\s*(.*?)\s*}'
    components = {}
    for comp_match in re.finditer(pattern, input_adl, re.DOTALL | re.MULTILINE):
        component = comp_match.group(1)
        body = comp_match.group(2)
        ports = re.findall(r'port\s+(\w+)\s*\(\)\s*=\s*(\w+)\s*->\s*(\w+)\s*\(\)\s*;', body)
        for port_name, event, port in ports:
            components[f"{component}.{port_name}"] = event
    component_ports = components

    """Generate the assertion based on the given path and ADL."""
    assertions = []
    # Display all paths
    for path in paths: 
        initial_port = path[0]
        final_port = path[-1]
        # Find corresponding events
        initial_event = component_ports.get(initial_port, "unknown_event")
        final_event = component_ports.get(final_port, "unknown_event")
        # Generate the assertion
        assertion = f"assert {system_name} |= [] ({initial_port}.{initial_event} -> <> {final_port}.{final_event});"
        assertions.append(assertion)
    return assertions
