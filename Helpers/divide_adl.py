import re
import requests
from preprocessing import load_adl, preprocess_with_adl, identify_liveness_assert_with_adl

def verify_adl(adl_with_assertions):
    url = "http://10.211.55.4:8090/api/adlapi/verify"  # Update with your API's endpoint
    data = {
        "model": "test",
        "code": adl_with_assertions
    }

    try:
        response = requests.post(url, json=data)
        #print("Response Status Code:", response.status_code)
        #print("Response Data:", response.json())  # If the response is JSON
        VS = response.json()
    except Exception as e:
        print("Error occurred:", e)
        return "error"
    return VS


def extract_attach_statements(adl_text):
    """
    Extracts all 'attach' statements from the ADL text and returns them as a list.

    Args:
        adl_text (str): Full ADL text containing attach statements.

    Returns:
        List[str]: A list of attach statements as strings.
    """
    # Regex pattern to match all attach statements
    attach_pattern = r'attach\s+[\w\.]+\(\)\s*=\s*.*?;'

    # Find all attach statements (including multi-branch)
    attach_statements = re.findall(attach_pattern, adl_text, re.DOTALL)

    # Clean up and return the attach statements
    return [stmt.strip() for stmt in attach_statements]
def parse_paths(paths_text):
    """
    Parses the input paths text and returns a list of paths, where each path
    is a list of nodes.
    """
    paths = []
    lines = paths_text.strip().split("\n")
    for line in lines:
        # Extract the path using regex
        match = re.search(r'Path \d+:\s*(.+)', line)
        if match:
            path_str = match.group(1)
            nodes = [node.strip() for node in path_str.split("->")]
            paths.append(nodes)
    return paths

def extract_lhs(attach_statement):
    """
    Extracts the component port from an attach statement.
    For example, "attach PassengerUI.call() = callwire.requester(10);"
    returns "PassengerUI.call".
    """
    m = re.search(r'^attach\s+([\w\.]+)\(\)\s*=', attach_statement)
    if m:
        return m.group(1)
    return None

def select_attachments_for_paths(paths, attach_statements):
    """
    For each path, selects the relevant attach statements based on the nodes in the path.
    Avoids duplicates.
    """
    # Build a dictionary mapping component ports to attach statements
    attach_dict = {}
    for stmt in attach_statements:
        comp_port = extract_lhs(stmt)
        if comp_port:
            attach_dict[comp_port] = stmt

    # Iterate over each path and collect relevant attach statements
    all_selected_attachments = []

    for path_idx, path_nodes in enumerate(paths):
        selected_attachments = set()  # To avoid duplicates
        for node in path_nodes:
            if node in attach_dict:
                selected_attachments.add(attach_dict[node])
        all_selected_attachments.append((path_idx, list(selected_attachments)))

    return all_selected_attachments

def fix_last_brace_indentation(adl_code: str):
    lines = adl_code.split("\n")
    
    # Find the last non-empty line that contains only '}'
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() == "}":
            lines[i] = "}"
            break
    
    return "\n".join(lines)

def update_adl_with_new_attachments(original_adl, new_attachments, new_execute_line):
    cleaned_adl = re.sub(r'attach\s+[\w\.]+\(\)\s*=.*?;\s*', '', original_adl, flags=re.DOTALL)
    cleaned_adl = re.sub(r'execute\s+[^;\n]+;?', '', cleaned_adl, flags=re.DOTALL)
    cleaned_adl = re.sub(r'\n\s*\n', '\n', cleaned_adl).strip()

    system_block_pattern = r'(system\s+\w+\s*{)'
    match = re.search(system_block_pattern, cleaned_adl)
    if match:
        # Prepare the new attachments string
        new_attachments_str = "\n"+ new_attachments + "\n\t " + new_execute_line

        # Insert new attachments inside the system block
        updated_adl = re.sub(system_block_pattern, r'\1' + new_attachments_str, cleaned_adl)

        declare_pattern = r'(declare\s+\w+\s*=\s*\w+\s*;)'  # Matches all declare statements
        declares = list(re.finditer(declare_pattern, cleaned_adl, flags=re.MULTILINE))

        if declares:
            last_declare = declares[-1]
            # Insert new attachments after the last declare
            insertion_point = last_declare.end()
            updated_adl = cleaned_adl[:insertion_point] + new_attachments_str + cleaned_adl[insertion_point:]
    else:
        raise ValueError("System block not found in ADL.")
    
    # the last bracket will have influence on generated paths
    updated_adl = fix_last_brace_indentation(updated_adl)

    return updated_adl

def get_divided_adls(adl_text):
    # Input: Paths
    paths = preprocess_with_adl(adl_text)

    for idx, path in enumerate(paths, 1):
        print(f"Path {idx}: {' -> '.join(path)}") 
    # Input: Attachments
    attach_statements = extract_attach_statements(adl_text)

    # Extract attach statements for each path
    selected_attachments = select_attachments_for_paths(paths, attach_statements)

    for path_idx, attaches in selected_attachments:
        # Generate dynamic variable name (e.g., "attachments_path1")
        var_name = f"attachments_path{path_idx}"

        # Format the attachment string
        attachment_string = f"\n\t ".join(attaches)
        attachment_string = "\t " + attachment_string

        # Dynamically create global variable
        globals()[var_name] = attachment_string

    for i in range(len(selected_attachments)):
        var_name = f"attachments_path{i}"
        if var_name in globals():
            
            lhs_list = [extract_lhs(stmt) for stmt in selected_attachments[i][1]]
            lhs_list = [f"{lhs}()" for lhs in lhs_list]
            execute_line = "execute " + " || ".join(lhs_list) + ";"
            globals()[var_name] = update_adl_with_new_attachments(adl_text, globals()[var_name], execute_line)
            # for the divided system, generate assertions by refering to the divided' system paths
            assertions = identify_liveness_assert_with_adl(globals()[var_name])
            # for ass in assertions:
            #     print(ass)
            globals()[var_name] += "\n" + "\n".join(assertions)
            #print(globals()[var_name])
            
    return selected_attachments

def get_verification_results(file_name):
    adl_text = load_adl(file_name)
    selected_attachments = get_divided_adls(adl_text)
    final_result = "valid"
    # if there is one invalid, the whole adl is invalid
    for i in range(len(selected_attachments)):
        var_name = f"attachments_path{i}"
        if var_name in globals():
            # verify the divided ADLs with their own Assertions
            VS = verify_adl(globals()[var_name])
            if isinstance(VS, dict):
                final_result = "invalid"
                print("-"*50)
                print(VS['Message'])
                print(globals()[var_name])
                print("-"*50)
            else:
                for vs in VS:
                    if vs['result'] == "invalid":
                        final_result = "invalid"
                        print("-"*50)
                        print(vs['result'])
                        print(vs['fullResultString'])
                        #print(globals()[var_name])
                        print("-"*50)
    return final_result

def get_verification_results_with_adl(adl_text):
    selected_attachments = get_divided_adls(adl_text)
    final_result = "valid"
    print("-"*50)
    # if there is one invalid, the whole adl is invalid
    for i in range(len(selected_attachments)):
        var_name = f"attachments_path{i}"
        if var_name in globals():
            # verify the divided ADLs with their own Assertions
            VS = verify_adl(globals()[var_name])
            if isinstance(VS, dict):
                final_result = "invalid"
                #print("-"*50)
                print(VS['Message'])
                print(globals()[var_name])
                print("-"*50)
            else:
                for vs in VS:
                     if vs['result'] == "invalid":
                        final_result = "invalid"
                        print("-"*50)
                        # print(vs['result'])
                        print(vs['fullResultString'])
                        print(globals()[var_name])
                        print("-"*50)
    return final_result

