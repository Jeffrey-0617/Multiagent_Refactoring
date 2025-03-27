import re

def add_component(wright_code, component_name):
    # Check if the component already exists
    component_pattern = rf"\bcomponent\s+{component_name}\s*{{"
    if re.search(component_pattern, wright_code):
        return wright_code  # No changes needed, component already exists

    # Format the new component
    new_component = f"component {component_name} {{\n}}\n\n"

    # Regex pattern to find the system declaration
    system_pattern = r"(system\s+\w+\s*{)"
    
    # Find the system declaration
    match = re.search(system_pattern, wright_code)

    if match:
        # Insert the new component before the system block
        modified_code = wright_code[:match.start()] + new_component + wright_code[match.start():]
    else:
        # If no system block is found, append at the end
        modified_code = wright_code.strip() + "\n\n" + new_component

    return modified_code

def add_port_to_component(wright_code, component_name, port_name, process_sequence):
    # Ensure the port is correctly formatted
    new_port = f"port {port_name}() = {process_sequence};\n"

    # Find the component definition using a regex pattern
    component_pattern = rf"(component\s+{component_name}\s*{{([\s\S]*?)}})"
    match = re.search(component_pattern, wright_code)

    if not match:
        return add_port_to_component(add_component(wright_code, component_name), component_name, port_name, process_sequence)
        #raise ValueError(f"Component '{component_name}' not found in the provided Wright# system.")

    # Extract the existing component content
    component_block = match.group(1)
    component_body = match.group(2)
    
    # if port exists, do not add, avoid duplicated ports
    port_pattern = rf"port\s+{port_name}\s*\(\)\s*="
    if re.search(port_pattern, component_body):
        return wright_code

    # Append the new port before the closing '}'
    modified_component = f"component {component_name} {{{component_body} \t {new_port}}}" 

    # Replace the old component with the modified version
    modified_code = wright_code.replace(component_block, modified_component)

    return modified_code

def delete_port_from_component(wright_code, component_name, port_name):
    # Find the component definition using a regex pattern
    component_pattern = rf"(component\s+{component_name}\s*{{([\s\S]*?)}})"
    match = re.search(component_pattern, wright_code)

    if not match:
        return wright_code
        #raise ValueError(f"component '{component_name}' not found in the provided Wright# system.")

    # Extract the existing component content
    component_block = match.group(1)
    component_body = match.group(2)
    
    # Remove the specified port while preserving other ports
    port_pattern = rf"^\s*port\s+{port_name}\s*\(.*?\)\s*=\s*.*?;\s*$"
    modified_body = re.sub(port_pattern, "", component_body, flags=re.MULTILINE).strip()
  
    # Ensure correct formatting
    if not modified_body:
        modified_component = f"component {component_name} {{\n}}"
    else:
        modified_component = f"component {component_name} {{\n\t {modified_body}\n}}"

    # Replace the old component with the modified version
    modified_code = wright_code.replace(component_block, modified_component)

    return modified_code

def delete_component(wright_code, component_name):
    # Regex pattern to match the full component block
    component_pattern = rf"\n*component\s+{component_name}\s*{{[\s\S]*?}}\n*"

    # Remove the component from the Wright# system
    modified_code = re.sub(component_pattern, "\n", wright_code, flags=re.MULTILINE).strip()

    return modified_code

def add_role_to_connector(wright_code, connector_name, role_name, process_sequence):
    # Ensure the role is correctly formatted
    new_role = f"role {role_name}() = {process_sequence};\n"

    # Find the connector definition using a regex pattern
    connector_pattern = rf"(connector\s+{connector_name}\s*{{([\s\S]*?)}})"
    match = re.search(connector_pattern, wright_code)

    if not match:
        return add_role_to_connector(add_connector(wright_code, connector_name), connector_name, role_name, process_sequence)
        #raise ValueError(f"connector '{connector_name}' not found in the provided Wright# system.")

    # Extract the existing connector content
    connector_block = match.group(1)
    connector_body = match.group(2)

    # if role exists, do not add, avoid duplicated ports
    role_pattern = rf"role\s+{role_name}\s*\(\)\s*="
    if re.search(role_pattern, connector_body):
        return wright_code

    # Append the new role before the closing '}'
    modified_connector = f"connector {connector_name} {{{connector_body}\t {new_role}}}" 

    # Replace the old connector with the modified version
    modified_code = wright_code.replace(connector_block, modified_connector)

    return modified_code

def add_connector(wright_code, connector_name):
    # Check if the component already exists
    connector_pattern = rf"\bconnector\s+{connector_name}\s*{{"
    if re.search(connector_pattern, wright_code):
        return wright_code  # No changes needed, connector already exists

    # Format the new connector
    new_connector = f"connector {connector_name} {{\n}}\n\n"

    # Regex pattern to find the system declaration
    system_pattern = r"(system\s+\w+\s*{)"
    
    # Find the system declaration
    match = re.search(system_pattern, wright_code)

    if match:
        # Insert the new connector before the system block
        modified_code = wright_code[:match.start()] + new_connector + wright_code[match.start():]
    else:
        # If no system block is found, append at the end
        modified_code = wright_code.strip() + "\n\n" + new_connector

    return modified_code

def delete_role_from_connector(wright_code, connector_name, role_name):
    # Find the connector definition using a regex pattern
    connector_pattern = rf"(connector\s+{connector_name}\s*{{([\s\S]*?)}})"
    match = re.search(connector_pattern, wright_code)

    if not match:
        return wright_code
        #raise ValueError(f"Connector '{connector_name}' not found in the provided Wright# system.")

    # Extract the existing connector content
    connector_block = match.group(1)
    connector_body = match.group(2)
    
    # Remove the specified role while preserving other roles
    role_pattern = rf"^\s*role\s+{role_name}\s*\(.*?\)\s*=\s*.*?;\s*$"
    modified_body = re.sub(role_pattern, "", connector_body, flags=re.MULTILINE).strip()
  
    # Ensure correct formatting
    if not modified_body:
        modified_connector = f"connector {connector_name} {{\n}}"
    else:
        modified_connector = f"connector {connector_name} {{\n\t {modified_body}\n}}"

    # Replace the old connector with the modified version
    modified_code = wright_code.replace(connector_block, modified_connector)

    return modified_code


def delete_connector(wright_code, connector_name):
    # Regex pattern to match the full connector block
    connector_pattern = rf"\n*connector\s+{connector_name}\s*{{[\s\S]*?}}\n*"

    # Remove the connector from the Wright# system
    modified_code = re.sub(connector_pattern, "\n", wright_code, flags=re.MULTILINE).strip()

    return modified_code

def add_attachment(wright_code, component_name, port_name, connector_name, role_name, parameters=None):
    # Format the new attachment role
    new_attachment = f"{connector_name}.{role_name}()"
    if parameters:
        new_attachment = f"{connector_name}.{role_name}({parameters})"

    # Improved regex to find existing attachment lines
    attach_pattern = rf"(attach\s+{component_name}\.{port_name}\(.*?\)\s*=\s*)(.*?)(;)"
    match = re.search(attach_pattern, wright_code, re.MULTILINE)

    if match:
        # Manually extract everything after '=' until the first ';'
        start_index = match.start(2)  # Get the position where the attachment starts
        end_index = wright_code.find(";", start_index)  # Find the next semicolon

        if end_index == -1:
            raise ValueError("Malformed attachment statement: missing semicolon.")

        # Extract full attachment content
        existing_attachments = wright_code[start_index:end_index].strip()

        # Convert the attachments to a list
        attachment_list = [att.strip() for att in existing_attachments.split("<*>")]

        # Remove parameters inside parentheses
        cleaned_attachment_list = [re.sub(r"\(.*?\)", "()", att) for att in attachment_list]
        
        # Check if the attachment already exists
        if re.sub(r"\(.*?\)", "()", new_attachment) in cleaned_attachment_list:
            return wright_code  # No changes needed, attachment already exists

        # Append the new role using <*> and update the attach statement
        attachment_list.append(new_attachment)
        updated_attachments = " <*> ".join(attachment_list)
        
        # Construct the new full statement
        modified_code = wright_code[:start_index] + updated_attachments + wright_code[end_index:]

    else:
        # Otherwise, add a new attach statement
        attach_line = f"\t attach {component_name}.{port_name}() = {new_attachment};\n"

        # Find the "system" block and insert the new attachment
        system_pattern = r"(system\s+\w+\s*{([\s\S]*?)\n})"
        system_match = re.search(system_pattern, wright_code)

        if not system_match:
            raise ValueError("System block not found in the provided Wright# system.")

        system_block = system_match.group(1)
        system_body = system_match.group(2)
        system_name = system_match.group(0).split()[1]  # Extract system name dynamically

        # Append the new attachment before the closing '}'
        modified_system = f"system {system_name} {{\n{system_body.strip()}\n{attach_line}}}"

        # Replace the old system block with the modified version
        modified_code = wright_code.replace(system_block, modified_system)

    return modified_code

def delete_attachment(wright_code, component_name, port_name, connector_name, role_name):
    # Regex pattern to find an existing attachment
    attach_pattern = rf"(attach\s+{component_name}\.{port_name}\(.*?\)\s*=\s*([\w\.\(\)]+(?:\s*<\*>.*?)*));"

    # Check if the attachment exists
    match = re.search(attach_pattern, wright_code)

    if not match:
        return wright_code

    existing_attachment = match.group(1)
    attachment_body = match.group(2)  # The roles attached

    # Role pattern to remove the specified role
    role_pattern = rf"(\s*<\*>\s*)?{connector_name}\.{role_name}\(.*?\)"

    # Case 1: Role is the only one in the attachment -> Remove entire attachment
    if not re.search(r"<\*>", attachment_body):  
        modified_code = re.sub(rf"^\s*{re.escape(existing_attachment)};\s*\n?", "", wright_code, flags=re.MULTILINE)
    else:
        # Case 2: Role is at the front -> Ensure next role remains valid
        if re.match(role_pattern, attachment_body.strip()):
            modified_attachment = re.sub(role_pattern, "", attachment_body, count=1).lstrip("<*> ").strip()
        else:
            # Case 3: Role is in the middle or last -> Just remove it
            modified_attachment = re.sub(role_pattern, "", attachment_body, count=1).strip()

        # Ensure correct formatting
        modified_attachment = f"attach {component_name}.{port_name}() = {modified_attachment}"

        # Replace the old attachment with the modified version
        modified_code = wright_code.replace(existing_attachment, modified_attachment)

    return modified_code


def add_declare_connector(wright_code, connector_name, connector_type):
    # Format the new declare statement
    new_declare = f"    declare {connector_name} = {connector_type};\n"

    # Find the "system" block
    system_pattern = r"(system\s+\w+\s*{([\s\S]*?)\n})"
    match = re.search(system_pattern, wright_code)

    if not match:
        raise ValueError("System block not found in the provided Wright# system.")

    # Extract the existing system content
    system_block = match.group(1)
    system_body = match.group(2)
    system_name = match.group(0).split()[1]  # Extract system name dynamically

    # Check if the connector is already declared
    declare_pattern = rf"\s*declare\s+{connector_name}\s*="
    if re.search(declare_pattern, system_body):
        # raise ValueError(f"Connector '{connector_name}' is already declared.")
        return wright_code
        

    # Append the new declare statement before the closing '}'
    modified_system = f"system {system_name} {{\n{new_declare}{system_body.strip()}\n}}"

    # Replace the old system block with the modified version
    modified_code = wright_code.replace(system_block, modified_system)

    return modified_code


def delete_declare_connector(wright_code, connector_name):
    # Regex pattern to find the declare statement
    declare_pattern = rf"^\s*declare\s+{connector_name}\s*=\s*\w+;\s*\n?"

    # Check if the connector is declared
    if not re.search(declare_pattern, wright_code, flags=re.MULTILINE):
        return wright_code
        #raise ValueError(f"Connector '{connector_name}' is not declared in the system.")

    # Remove the declaration
    modified_code = re.sub(declare_pattern, "", wright_code, flags=re.MULTILINE).strip()

    return modified_code


def add_execute_component(wright_code, component_name, port_name):

    # Find the system block (dynamic system name)
    system_pattern = r"(system\s+\w+\s*{([\s\S]*?)\n})"
    match = re.search(system_pattern, wright_code)

    if not match:
        raise ValueError("System block not found in the provided Wright# system.")

    system_block = match.group(1)
    system_name = match.group(0).split()[1]  # Extract system name dynamically
    system_body = match.group(2)

    # New execute command to add
    new_execute = f"{component_name}.{port_name}()"

    # Regex to find the execute statement and remove trailing semicolon if present
    execute_pattern = r"(execute\s+([^\n;]+)(?:\s*\|\|\s*[^\n;]+)*)(\s*;?)"
    execute_match = re.search(execute_pattern, system_body, re.MULTILINE)

    if execute_match:
        # Remove the trailing semicolon if present
        existing_execute = execute_match.group(2).strip()
        # Check if new_execute is already present
        execute_list = set(existing_execute.split(" || "))
        if new_execute in execute_list:
            return wright_code  # ✅ No changes needed, already exists
            
        modified_execute = f"execute {existing_execute} || {new_execute};\n"
        modified_code = re.sub(execute_pattern, modified_execute, wright_code)
    else:
        # If execute does not exist, create a new execute statement
        new_execute_line = f"\t execute {new_execute};\n"
        modified_system = f"system {system_name} {{\n{system_body.strip()}\n{new_execute_line}}}"
        modified_code = wright_code.replace(system_block, modified_system)

    return modified_code

def delete_execute_component(wright_code, component_name, port_name):

    # Format the execute component pattern
    execute_port_pattern = rf"(?:{component_name}\.{port_name}\(\)\s*\|\|\s*|\|\|\s*{component_name}\.{port_name}\(\)|{component_name}\.{port_name}\(\))"

    # Regex pattern to find execute statements
    execute_pattern = r"(execute\s+[^\n]+(?:\n\s*\|\|[^\n]+)*)(\s*;?)"

    matches = list(re.finditer(execute_pattern, wright_code, re.MULTILINE))

    if not matches:
        return wright_code
        raise ValueError("No execute statement found in the provided Wright# system.")

    # Process each execute statement found
    for match in matches:
        existing_execute = match.group(1).strip()

        # Remove the specified component's port
        modified_execute = re.sub(execute_port_pattern, "", existing_execute).strip()

        # If execute statement becomes empty, remove it entirely
        if re.match(r"execute\s*$", modified_execute):
            modified_code = wright_code.replace(match.group(0), "").strip()
        else:
            modified_code = wright_code.replace(existing_execute, modified_execute)

    return modified_code


def secure_execution(wright_code):

    # Normalize text (strip excess spaces and tabs)
    normalized_text = "\n".join(line.strip() for line in wright_code.split("\n"))

    # Step 1: Extract attach lines manually
    attach_lines = [line for line in normalized_text.split("\n") if line.startswith("attach ")]

    # Step 2: Parse component.port pairs from extracted attach lines
    attached_ports = set()
    for line in attach_lines:
        parts = line.split("=")[0].strip().split()
        if len(parts) >= 2:
            component_port = parts[1].strip().replace("()", "")  # Remove parentheses if present
            if "." in component_port:
                attached_ports.add(tuple(component_port.split(".")))

    # Step 3: Find the existing execute line
    execute_pattern = r"(execute\s+([^\n;]+(?:\n\s*\|\|\s*[^\n;]+)*))\s*;"
    execute_match = re.search(execute_pattern, wright_code, re.MULTILINE)

    if execute_match:
        existing_execute = execute_match.group(1).strip()  # Extract existing execute statement
        execute_ports = set(re.findall(r"(\w+)\.(\w+)\(\)", existing_execute))  # Extract (component, port) pairs

        # Identify missing (component, port) pairs to add
        missing_ports = attached_ports - execute_ports

        # Identify extra (component, port) pairs to remove
        extra_ports = execute_ports - attached_ports

        if (not missing_ports) and (not extra_ports):
            return wright_code

        # Remove unwanted ports from execute line
        for comp, port in extra_ports:
            existing_execute = re.sub(rf"\s*\|\|\s*{comp}\.{port}\(\)", "", existing_execute)  # Remove middle instances
            existing_execute = re.sub(rf"{comp}\.{port}\(\)\s*\|\|\s*", "", existing_execute)  # Remove front instances
            existing_execute = re.sub(rf"{comp}\.{port}\(\)", "", existing_execute)  # Remove single instances

        # Ensure we don't leave `execute` empty
        if existing_execute.strip() == "execute":
            existing_execute = ""  # Remove execute line entirely if empty

        if missing_ports:
            # Extend the execute line with missing ports
            new_executions = " || ".join([f"{comp}.{port}()" for comp, port in missing_ports])
            existing_execute = f"{existing_execute} || {new_executions};\n" if existing_execute else f"execute {new_executions};\n"
            
        # Ensure execute ends with a semicolon (;)
        existing_execute = "\t " + existing_execute.rstrip()
        if existing_execute and not existing_execute.endswith(";"):
            existing_execute += ";"

        # Replace the old execute statement with the modified version
        if existing_execute:
            wright_code = re.sub(execute_pattern, existing_execute, wright_code, count=1)
        else:
            wright_code = re.sub(execute_pattern, "", wright_code, count=1)  # Remove execute line if empty

    else:
        # Step 4: Insert new execute line within the system definition if it doesn't exist
        system_pattern = r"(system\s+\w+\s*{[\s\S]*?)(\n})"
        system_match = re.search(system_pattern, wright_code, re.MULTILINE)

        if system_match and attached_ports:
            system_body = system_match.group(1)  # System definition content before the last `}`
            new_execute_line = "\t execute " + " || ".join([f"{comp}.{port}()" for comp, port in attached_ports]) + ";\n"
            modified_system = system_body.strip() + "\n" + new_execute_line + "\n}"  # Insert before final `}`

            # Replace system block with modified version
            wright_code = re.sub(system_pattern, modified_system, wright_code, count=1)

    return wright_code
    