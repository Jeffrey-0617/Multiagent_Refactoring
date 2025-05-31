# ----------------------
# GRAG execution
# ----------------------
from graphrag.cli.query import run_local_search
from pathlib import Path
from auxiluary import extract_assert_statements, match_asserts_to_paths
from preprocessing import preprocess_with_adl
from divide_adl import get_verification_results_with_adl


def get_validation_assert(paths: str, ADL: str, new_requirement: str):
    # Define the root directory dynamically
    grag_dir = Path("INPUT YOUR GRAG DIRECTORY HERE")

    # Construct the prompt
    query = f"""
You are an expert in formal verification and Wright# ADL. Based on the given input, your task is to generate liveness properties in the form of assert statements to verify the system behavior against the new requirements.
The liveness properties should be in the form: assert systemname |= [] (initial_componentname.portname.eventname -> <> target_componentname.portname.eventname)

You are provided with:
1. System Execution Paths:
{paths}

2. Wright# ADL Specification:
{ADL}

3. New Functional Requirement:
{new_requirement}

Generate the liveness properties for the new functional requirement based on your understanding of the given systems (understanding will come from the paths and ADL specification).
Only Output the generated properties, nothing else
"""
    response, context= run_local_search(
    query=query,
    root_dir=grag_dir,
    community_level=2,
    response_type="multiple paragraphs",
    streaming = False,
    data_dir = grag_dir/"output",
        config_filepath = grag_dir/"settings.yaml"
    )
    return response

def validation_verification(adl, new_requirement):
    # Validation
    # Generate the Paths
    # verification
    verification_result = get_verification_results_with_adl(adl)     

    # Validation
    current_paths = ""
    paths = preprocess_with_adl(adl)
    for idx, path in enumerate(paths, 1):
        current_paths += f"Path {idx}: {' -> '.join(path)}\n"
        
    # generate the assert statements for validation
    response = get_validation_assert(current_paths, adl, new_requirement)
    asserts = extract_assert_statements(response)
    results = match_asserts_to_paths(asserts, paths)
    print("---------------------------------Results:-------------------------------\n", results)
    
    # if the assert statement doesn't belong to any path, it indicates the behavior cannot be achieved by the system
    if asserts == [] and verification_result == "valid":
        return f"Validation: Failed; Verification:{verification_result}\n{adl}"
    elif asserts == [] and verification_result == "invalid":
        return f"Both Validation and Verification:{verification_result}\n{adl}"
    
    for stmt, result in results:
        if verification_result == "invalid":
            exec_result = f"Both Validation and Verification:{verification_result}\n{adl}"
            break;
        else:
            if result == "not existing":
                exec_result = f"Validation: Failed; Verification:{verification_result}\n{adl}"
                break;
            else:
                exec_result = f"Both Validation and Verification:{verification_result}\n{adl}"

    return exec_result