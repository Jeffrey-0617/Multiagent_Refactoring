import pandas as pd
from openai import OpenAI
from preprocessing import load_adl, preprocess_with_adl
import re
import sys
sys.path.append('../Helpers')
from querygrag import validation_verification

def get_adl(text):
    # Regular expression to capture ADL content
    adl_pattern = re.compile(r'```.*?\n(.*?)```', re.DOTALL)
    
    # Search for ADL block
    match = adl_pattern.search(text)
    
    if match:
        adl_content = match.group(1).strip()
    else:
        return "No ADL content found."
    
    adl_content = match.group(1).strip()

    # Step 2: Remove any lines starting with a backslash, regardless of indentation
    cleaned_lines = []
    for line in adl_content.splitlines():
        # Use lstrip() to ignore leading whitespace, then check if it starts with "\"
        if not line.lstrip().startswith("\\"):
            cleaned_lines.append(line)

    # Step 3: Rejoin the cleaned lines into the final ADL content
    cleaned_adl = "\n".join(cleaned_lines).strip()

    return cleaned_adl


def llm_for_refactoring(adl, new_requirement):
    formatted_paths = ""
    paths = preprocess_with_adl(adl)
    for idx, path in enumerate(paths, start=1):
        formatted_paths += f"Path {idx}: {path}\n"
    
    client = OpenAI(api_key = "YOUR_OPENAI_API_KEY")
    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": f"""You are an expert for refactoring the architecture design model in Wright#. Your task is to modify the design model based on the new requirement. The Output only contains the script of refactored architecture design model."""},
            {"role": "user", "content": f""" 
             Step by Step to output the refactored ADL based on the new requirement.
            ### Step 1: Understand the Current ADL System (Structural and Behavioral Analysis) by reading the provided details information** 
                        - understand the components, ports, connector variables and their roles.
                        - understand the system interations defined by attach statements
             
            ### Step 2: Comprehend the Provided New Requirement and the system execution paths
            
            ### Step 3: Plan the modifications step by step
                    1. Identify All Required Structural Changes 
                    
 
                    2. Update all necessary attach statements to reflect the new interations 
                    
            ### Final Step: Output the refactored ADL
                    
            Please ensure that the output only contains the refactored ADL.
            
            Current ADL:\n{adl}
            New requirement:  {new_requirement}
            System execution paths:\n {formatted_paths}"""}
            ],
        model="gpt-4o"
    )

    return response
    
def append_to_excel(adl_file_name, new_requirement, result, run_id, file_path):
    # Create a DataFrame for the new entry
    new_entry = pd.DataFrame({
        "ADL File Name": [adl_file_name],
        "New Requirement": [new_requirement],
        "Execution Result": [result],
        "Run ID": [run_id]
    })
    
    # Append to existing file without overwriting
    try:
        existing_df = pd.read_excel(file_path)
        updated_df = pd.concat([existing_df, new_entry], ignore_index=True)
    except FileNotFoundError:
        updated_df = new_entry
    
    updated_df.to_excel(file_path, index=False)
    print("Execution logged in Excel.")

# Load Excel data
input_file = "../Refactoring_data.xlsx"  # Change this to your actual Excel file name
df = pd.read_excel(input_file, engine="openpyxl")
df = df.iloc[12:31]  # Select rows from index 30 to 60 (inclusive)

# Loop through each row in the Excel file
for index, row in df.iterrows():
    adl_file_name = row["System"]  # Column containing ADL file names
    new_requirement = row["Requirement"]  # Column containing new requirements
    adl = load_adl(adl_file_name)

    # Run execution 8 times for each instance
    for run_id in range(1, 9):  # Runs each instance 10 times
        response = llm_for_refactoring(adl, new_requirement)
        refactored_adl = get_adl(response.choices[0].message.content)
        final_result = validation_verification(refactored_adl, new_requirement)
        output_file = "baseline_gpt4o_results.xlsx"
        append_to_excel(adl_file_name, new_requirement, final_result, run_id, output_file)
        print(f"Execution {run_id} completed for {adl_file_name}: {new_requirement}")
    