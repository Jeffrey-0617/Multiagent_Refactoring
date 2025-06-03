import re

def split_into_two_roles(connector_roles):
    input_roles = set()
    output_roles = set()
    for i in range(len(connector_roles)):
        input_roles.add(connector_roles[i][1])
        output_roles.add(connector_roles[i][2])
        if connector_roles[i][3] != None:
            output_roles.add(connector_roles[i][3])
    return input_roles, output_roles

def detect_output_role_issues(attachments, connector_roles):
    attached_ports = []
    attached_IR = []
    attached_OR = []
    matching_attachment_COR = []
    matching_attachment_CIR = []
    COR = None
    CT = None
    
    """Detects connectors with the same output role attached to multiple ports."""
    from collections import defaultdict

    connector_role_map = defaultdict(list)

    # get the output_roles from connector_roles
    input_roles, output_roles = split_into_two_roles(connector_roles)

    # Parse attachments to collect output roles per connector
    for line in attachments:
        match = re.match(r'attach\s+([\w.]+)\(\)\s*=\s*(.+);', line)
        if match:
            port = match.group(1)
            roles = re.findall(r'([\w]+)\.([\w]+)', match.group(2))
            for connector, role in roles:
                if role in output_roles:
                    connector_role_map[(connector, role)].append(port)
                    
                    
    # Find connectors with multiple ports using the same output role
    issues = []
    for (connector, role), ports in connector_role_map.items():
        if len(ports) > 1:
            issues.append({
                "connector": connector,
                "role": role,
                "ports": ports
            })
    # find corresponding input role
    CORs = []
    CIRs = []
    CTs = []
    if issues:
        for issue in issues:
            for i in range(len(connector_roles)):
                if issue['role'] == connector_roles[i][2] or issue['role'] == connector_roles[i][3]:
                    input_rolename = connector_roles[i][1]
                    connector_type = connector_roles[i][0]
            CORs.append(f"{issue['connector']}.{issue['role']}")
            CIRs.append(f"{issue['connector']}.{input_rolename}")
            CTs.append(f"{connector_type}")
    else:
        return issues, matching_attachment_CIR, matching_attachment_COR
        
    # find the attachement lines containing the target role
    for (CIR, COR) in zip(CIRs, CORs):
        for idx, line in enumerate(attachments, start=1):
            if CIR in line:
                matching_attachment_CIR.append(line)
            if COR in line:
                matching_attachment_COR.append(line)
    
    #from attachment COR and CIR, detete all the component.port pairs and connector.inputrole pairs and outputrole pairs
    # Parse attachments to collect output roles per connector
    for line in (matching_attachment_CIR + matching_attachment_COR):
        match = re.match(r'attach\s+([\w.]+)\(\)\s*=\s*(.+);', line)
        if match:
            attached_ports.append(match.group(1)) 
            roles = re.findall(r'([\w]+)\.([\w]+)(?:\((\d+)\))?', match.group(2))
            for connector, role, param in roles:
                role_with_params = f"{connector}.{role}({param})" if param else f"{connector}.{role}()"  # Append (23) if present
                if role in input_roles:  # Check role without ()
                    attached_IR.append(role_with_params)  # Append with (23) if exists
                if role in output_roles:  # Check role without ()
                    attached_OR.append(role_with_params)  # Append with (23) if exists
    attached_ports = list(set(attached_ports))
    attached_IR = list(set(attached_IR))
    attached_OR = list(set(attached_OR))
        
    return issues, matching_attachment_CIR, matching_attachment_COR

def extract_attach_statements(adl_text):
    """
    Extract all 'attach' statements from the ADL text into a list.
    
    Args:
        adl_text (str): The ADL source code as a string.
    
    Returns:
        list: A list of attach statements.
    """
    # Regular expression pattern to match attach statements
    pattern = r'attach\s+.*?;'
    
    # Find all matches using regex
    attach_statements = re.findall(pattern, adl_text)
    
    return attach_statements

def extract_assert_statements(text: str):
    """
    Extracts all 'assert' statements from a given block of text.

    Args:
        text (str): Input string containing possible assert statements.

    Returns:
        List[str]: A list of extracted assert statements.
    """
    # # Match lines that start with 'assert' and continue until the end of the line
    # pattern = r'assert\s.+?;'
    # matches = re.findall(pattern, text)
    # return matches

    # Match lines that start with 'assert' and continue until the end of the line
    pattern = r'^\s*assert\s.*$'
    matches = re.findall(pattern, text, flags=re.MULTILINE)
    return matches

def parse_assert_components(assert_stmt: str):
    """
    Extracts the source and target component.port from an assert statement.
    Example: 'PassengerUI.call.callride -> <> TripMgmt.accept.acknowledged'
    returns 'PassengerUI.call', 'TripMgmt.accept'
    """
    match = re.search(r'assert\s+\w+\s*\|=\s*\[\]\s*\((.*?)\s*->\s*<>?\s*(.*?)\)', assert_stmt)
    if match:
        src_parts = match.group(1).strip().split('.')[0:2]
        tgt_parts = match.group(2).strip().split('.')[0:2]
        return '.'.join(src_parts), '.'.join(tgt_parts)
    return None, None

def match_asserts_to_paths(asserts, paths):
    """
    Matches each assert to a path index if both source and target appear in the same path.
    Returns a list of (assert, path_index or 'not existing') tuples.
    """
    results = []
    for stmt in asserts:
        src, tgt = parse_assert_components(stmt)
        found = False
        for i, path in enumerate(paths):
            if src in path and tgt in path:
                # Check order only if both exist
                if path.index(src) < path.index(tgt):
                    results.append((stmt, i))
                    found = True
                    break
        if not found:
            results.append((stmt, "not existing"))
    return results