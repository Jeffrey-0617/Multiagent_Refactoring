import re
import random
from collections import defaultdict
from preprocessing import extract_connector_order, load_adl
from helper import secure_execution, add_port_to_component
from divide_adl import extract_lhs, extract_attach_statements

def extract_attach_statements(adl_text):
    # Regular expression pattern to match attach statements
    pattern = r'^\s*attach\b.*?;'
    attach_statements = re.findall(pattern, adl_text, flags=re.MULTILINE | re.DOTALL)
    return attach_statements

def extract_declarations(adl_text):
    pattern = r'^\s*declare\s+(\w+)\s*=\s*(\w+)\s*;'
    matches = re.findall(pattern, adl_text, flags=re.MULTILINE)
    declarations = {wire: connector for wire, connector in matches}
    return declarations

def split_into_two_roles(adl_text):
    connector_roles = extract_connector_order(adl_text)
    input_roles = set()
    output_roles = set()
    for i in range(len(connector_roles)):
        input_roles.add(connector_roles[i][1])
        output_roles.add(connector_roles[i][2])
        if connector_roles[i][3] != None:
            output_roles.add(connector_roles[i][3])
    return input_roles, output_roles

def find_rest_role_attachments(input_role, attachments, declarations, connector_roles):
    input_role = input_role.strip()
    
    # Extract the connector name and the role name from the input_role.
    try:
        connector, role_with_paren = input_role.split('.', 1)
    except ValueError:
        return {}
    role_name = role_with_paren.split('(')[0]  # e.g., "eventsubscriber"
    
    # Lookup the connector type using the declarations mapping.
    connector_type = declarations.get(connector)
    if not connector_type:
        return {}
    
    # Find the corresponding connector_roles entry for this connector type.
    matching_row = None
    for row in connector_roles:
        if row[0] == connector_type:
            matching_row = row
            break
    if not matching_row:
        return {}
    
    # Extract the roles from the row (ignoring the connector type).
    # Filter out any None values.
    roles = [r for r in matching_row[1:] if r is not None]
    
    # For a three-role connector, we expect three roles.
    # Remove the role that matches the input role.
    rest_roles = [r for r in roles if r != role_name]
    
    # For each remaining role, construct the expected output role string and find its attachment.
    result = {}
    for r in rest_roles:
        candidate = f"{connector}.{r}"
        found_attachment = None
        for attachment in attachments:
            if candidate in attachment:
                found_attachment = attachment.strip()
                break
        result[candidate] = found_attachment
    return result


def refine_attachments(extracted_attachments, primary_input_role, secondary_input_role, declarations, connector_roles):
    # Extract wire names from the input roles.
    primary_wire = primary_input_role.split('.')[0]    # e.g. "paywire"
    secondary_wire = secondary_input_role.split('.')[0]  # e.g. "authwire"
    
    # Determine the primary connector's output role.
    primary_connector_type = declarations.get(primary_wire)
    primary_output_role = None
    for row in connector_roles:
        if row[0] == primary_connector_type:
            primary_output_role = row[1]  # row[1] is the output role
            break
    if not primary_output_role:
        primary_output_role = ""  # fallback if not found

    def classify_role(role_str, connector_roles):
        role_str = role_str.strip()
        m = re.search(r'\.(\w+)\s*\(', role_str)
        if not m:
            return "unknown"
        role_name = m.group(1).lower()
        
        # Build a mapping from role names to their classification using connector_roles.
        role_mapping = {}
        for row in connector_roles:
            if row[1]:
                role_mapping[row[1].lower()] = "output"
            if row[2]:
                role_mapping[row[2].lower()] = "input"
            if len(row) > 3 and row[3]:
                role_mapping[row[3].lower()] = "input"
        
        return role_mapping.get(role_name, "unknown")
    
    refined_attachments = []
    
    # Pattern to split an attachment into left part, roles part, and trailing semicolon.
    attach_pattern = re.compile(r'^(attach\s+.+?=\s+)(.+)(;)$')
    for att in extracted_attachments:
        att = att.strip()
        m = attach_pattern.search(att)
        if not m:
            refined_attachments.append(att)
            continue
        
        left, roles_part, semicolon = m.group(1), m.group(2), m.group(3)
        # Split roles by the delimiter "<*>"
        roles = [r.strip() for r in roles_part.split("<*>")]
        new_roles = []
        for role in roles:
            if role.startswith(secondary_wire + "."):
                role_type = classify_role(role, connector_roles)
                if role_type == "output":
                    # Extract the parameter from the role.
                    param_match = re.search(r'\(([^)]+)\)', role)
                    param = param_match.group(1) if param_match else ""
                    # Replace with primary_wire + primary_output_role and keep the parameter.
                    new_role = f"{primary_wire}.{primary_output_role}({param})"
                    new_roles.append(new_role)
                elif role_type == "input":
                    # Drop input roles from the secondary wire.
                    continue
                else:
                    new_roles.append(role)
            else:
                new_roles.append(role)
                
        new_roles_part = " <*> ".join(new_roles) if new_roles else ""
        refined_att = left + new_roles_part + semicolon
        refined_attachments.append(refined_att)
    
    return refined_attachments

def replace_attachments_in_adl(adl_text, illegal_attachments, refined_attachments):
    updated_adl = adl_text

    # Delete each extracted (original) attachment from the ADL text.
    for extracted in illegal_attachments:
        updated_adl = updated_adl.replace(extracted, "")
    
    # CLEAN EMPTY LINES
    updated_adl = re.sub(r'\n\s*\n', '\n', updated_adl).strip()

    # Prepare a block of refined attachments.
    refined_block = "\t "+ "\n\t ".join(refined_attachments) + "\n"
    
    # Try to insert the refined attachments before an "execute" statement if one exists.
    execute_match = re.search(r'^\s*execute\b', updated_adl, flags=re.MULTILINE)
    if execute_match:
        insert_index = execute_match.start()
        updated_adl = updated_adl[:insert_index] + refined_block + updated_adl[insert_index:]
    else:
        # If no execute statement is found, append the refined attachments at the end.
        updated_adl = updated_adl.rstrip() + "\n" + refined_block
    # Remove any attachment lines where the right-hand side is empty.
    updated_adl = re.sub(r'^\s*attach\s+[^=]+=\s*;\s*\n?', '', updated_adl, flags=re.MULTILINE)
    
    return updated_adl

def detect_and_fix_violations(adl_text):
    output_roles, input_roles = split_into_two_roles(adl_text)
    attachments = extract_attach_statements(adl_text)
    declarations = extract_declarations(adl_text)
    connector_roles = extract_connector_order(adl_text)
    # Regex pattern to extract port and roles
    attachment_pattern = re.compile(r'attach\s+([\w.]+)\(\)\s*=\s*(.*?);')

    # Store port and attached input roles and their corresponding attachments
    port_input_roles = defaultdict(list)
    port_attachments = defaultdict(set)  # Using set to avoid duplicate attachments

    # Process attachments
    for attachment in attachments:
        match = attachment_pattern.search(attachment)
        if match:
            port = match.group(1)  # Extract port name
            roles = match.group(2).split('<*>')  # Handle multiple roles
            for role in roles:
                role = role.strip()
                role_name = role.split('(')[0].split('.')[-1]  # Extract role name
                if role_name in input_roles:
                    port_input_roles[port].append(role)  # Store full role reference
                    port_attachments[port].add(attachment)  # Store unique attachment

    # Identify ports with multiple input roles and their attachments using a for loop
    violations = {}
    for port, roles in port_input_roles.items():
        if len(roles) > 1:
            violations[port] = {
                'input_roles': roles,
                'attachments': list(port_attachments[port])
            }
            break
    
    # Build the result string
    if violations:
        for port, details in violations.items():
            illegal_attach = []
            for attach in details['attachments']:
                illegal_attach.append(attach)

            relevant_attach = find_rest_role_attachments(details['input_roles'][-1], attachments, declarations, connector_roles)
            for role, attach in relevant_attach.items():
                illegal_attach.append(attach)
            # get rid of None from the illegal attachment list
            illegal_attach = [x for x in illegal_attach if x != None]
            refined_attach = refine_attachments(illegal_attach, details['input_roles'][0], details['input_roles'][-1] , declarations, connector_roles)
            updated_adl = replace_attachments_in_adl(adl_text, illegal_attach, refined_attach)
    else:
        # No violation, detect_process_flag set to 0
        return adl_text, 0

    return updated_adl, 1

def fix_same_port_multiple_input_roles(adl_text):
    detect_process_flag =1 
    while detect_process_flag == 1:
        adl_text, detect_process_flag = detect_and_fix_violations(adl_text)
    
    # refine the execution line
    adl_text = secure_execution(adl_text)
    return adl_text

def remove_parameters_from_input_roles(adl_text):
    attachments_list = extract_attach_statements(adl_text)
    attachments_list = [att.lstrip("\t") for att in attachments_list]
    connector_roles = extract_connector_order(adl_text)
    # Build the set of input roles from the 3rd and 4th columns of connector_order_list.
    input_roles = set()
    for row in connector_roles:
        # row structure: [connector, role1, role2, role3] (role3 might be None)
        if len(row) > 2 and row[2]:
            input_roles.add(row[2])
        if len(row) > 3 and row[3]:
            input_roles.add(row[3])
    
    # Regex pattern to capture the connector and role with parameters.
    # This will match patterns like: connector.role(parameters)
    pattern = r'(\w+)\.(\w+)\(([^)]*)\)'
    
    new_attachments = []
    for att in attachments_list:
        def repl(match):
            connector = match.group(1)
            role = match.group(2)
            params = match.group(3)  # parameters (e.g., a number)
            if role in input_roles:
                # For input roles, remove the number but keep the parentheses empty.
                return f"{connector}.{role}()"
            else:
                # For non-input roles, leave the matched text unchanged.
                return match.group(0)
        new_att = re.sub(pattern, repl, att)
        new_attachments.append(new_att)
    
    # Replace the old attachments with new attachments
    adl_text = replace_attachments_in_adl(adl_text, attachments_list, new_attachments)
    return adl_text

def ensure_parameters_correct_output_roles(adl_text):
    attachments_list = extract_attach_statements(adl_text)
    attachments_list = [att.lstrip("\t") for att in attachments_list]
    connector_roles = extract_connector_order(adl_text)
    # Build the set of input roles from the 3rd and 4th columns of connector_order_list.
    output_roles = set()
    for row in connector_roles:
        output_roles.add(row[1])
        
    # Regex pattern to capture the connector and role with parameters.
    # This will match patterns like: connector.role(parameters)
    pattern = r'(\w+)\.(\w+)\(((?:[^()]*|\([^()]*\))*)\)'

    new_attachments = []
    for att in attachments_list:
        def repl(match):
            connector = match.group(1)
            role = match.group(2)
            params = match.group(3).strip()  # parameters (e.g., a number)
            if role in output_roles:
                # If it's not a number, assign a random one
                if params == '' or not params.isdigit():
                    random_number = random.randint(0, 100)
                    return f"{connector}.{role}({random_number})"
                else:
                    # Already valid number, return as is
                    return match.group(0)
            else:
                # For non-input roles, leave the matched text unchanged.
                return match.group(0)
        new_att = re.sub(pattern, repl, att)
        new_attachments.append(new_att)
    
    # Replace the old attachments with new attachments
    adl_text = replace_attachments_in_adl(adl_text, attachments_list, new_attachments)
    return adl_text


def get_defined_components_and_ports(adl_text):
    # Match component blocks
    component_pattern = r'component\s+(\w+)\s*{([^}]*)}'
    port_pattern = r'port\s+(\w+)\s*\('

    components_ports = {}

    for component_match in re.finditer(component_pattern, adl_text, re.DOTALL):
        component_name = component_match.group(1)
        ports_block = component_match.group(2)

        port_names = set()
        for port_match in re.finditer(port_pattern, ports_block):
            port_name = port_match.group(1)
            port_names.add(port_name)

        components_ports[component_name] = port_names

    return components_ports

def extract_fix_undefined_component_port(adl_text):
    # Extract all attachment statements and their left-hand sides (component.port)
    attachments = extract_attach_statements(adl_text)
    attached_component_ports = [extract_lhs(stmt.strip()) for stmt in attachments]
    
    # Retrieve all declared components and their ports
    components_with_ports = get_defined_components_and_ports(adl_text)

    for entry in attached_component_ports:
        # Validate the format before proceeding
        if "." not in entry:
            print(f"Skipping invalid attachment format: '{entry}'")
            continue

        component, port = entry.split(".")

        # If component is not defined OR port is not defined, flag it! 
        if component not in components_with_ports:
            adl_text = add_port_to_component(adl_text, component, port, f"{port}ed -> {port}()")
        elif port not in components_with_ports[component]:
            adl_text = add_port_to_component(adl_text, component, port, f"{port}ed -> {port}()")

        # fix it
    return adl_text

def reorder_input_roles_first(adl_text):
    # Extract all attachment statements from the ADL text
    attachments_list = extract_attach_statements(adl_text)
    attachments_list = [att.strip() for att in attachments_list]

    # Get input and output roles from the connector role definitions
    output_roles, input_roles = split_into_two_roles(adl_text)

    reordered_attachments = []

    for attach_stmt in attachments_list:
        # Match the attach statement structure: attach component.port = connector.role(...);
        lhs_rhs_match = re.match(r'attach\s+(.+?)\s*=\s*(.+);', attach_stmt)

        if not lhs_rhs_match:
            print(f"Skipping invalid attachment format: '{attach_stmt}'")
            continue

        lhs = lhs_rhs_match.group(1).strip()
        rhs = lhs_rhs_match.group(2).strip()

        # Split RHS into individual connector.role(param) items
        role_parts = [role.strip() for role in rhs.split('<*>')]

        # Separate input roles and other roles
        input_role_parts = []
        other_role_parts = []

        for role_part in role_parts:
            role_match = re.match(r'(\w+)\.(\w+)\(.*?\)', role_part)

            if not role_match:
                print(f"Skipping invalid role format: '{role_part}'")
                other_role_parts.append(role_part)
                continue

            role_name = role_match.group(2)

            if role_name in input_roles:
                input_role_parts.append(role_part)
            else:
                other_role_parts.append(role_part)

        # Combine input roles first, followed by output roles (or others)
        reordered_roles = input_role_parts + other_role_parts

        # Rebuild the new attach statement
        new_rhs = ' <*> '.join(reordered_roles)
        new_attach_stmt = f'attach {lhs} = {new_rhs};'

        reordered_attachments.append(new_attach_stmt)

    # Replace old attachments with reordered ones in the ADL text
    updated_adl_text = replace_attachments_in_adl(adl_text, attachments_list, reordered_attachments)

    return updated_adl_text
