import os
import re
import uuid
from typing import Optional, Literal, List
from openai import OpenAI

from pydantic import BaseModel, Field
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import (
    HumanMessage,
    SystemMessage,
    AIMessage,
    BaseMessage,
)
from langgraph.graph import StateGraph, MessagesState, END, START
from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import MessagesPlaceholder

# Import necessary classes from LangChain
from langchain.chat_models import ChatOpenAI
from langchain.chains import LLMChain
from langchain.prompts.chat import (
    ChatPromptTemplate,
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
)
from langchain.schema import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.tools import tool
import requests
from preprocessing import extract_connector_order, get_extended_paths_with_connector_info, load_adl
from postprocessing import replace_attachments_in_adl, fix_same_port_multiple_input_roles, remove_parameters_from_input_roles, ensure_parameters_correct_output_roles, extract_fix_undefined_component_port, reorder_input_roles_first
from divide_adl import get_verification_results_with_adl
from auxiluary import detect_output_role_issues, extract_attach_statements
from helper import add_port_to_component, add_component, delete_port_from_component, delete_component
from helper import add_role_to_connector, add_connector, delete_role_from_connector, delete_connector
from helper import add_attachment, delete_attachment, add_declare_connector, delete_declare_connector, add_execute_component, delete_execute_component
from helper import secure_execution

os.environ["LANGCHAIN_API_KEY"] = "YOUR_LANGCHAIN_API_KEY"
os.environ["OPENAI_API_KEY"] = "YOUR_OPEN_AI_API_KEY"
os.environ["LANGCHAIN_TRACING_V2"] = "true"

os.environ["LANGCHAIN_PROJECT"] = "project-with-threads"
os.environ["session_id"] = f"thread-id-{run_id}"
os.environ["LANGSMITH_EXTRA"] = str({"project_name": os.environ["LANGCHAIN_PROJECT"], "metadata":{"session_id": os.environ["session_id"]}})

# Initialize the ChatOpenAI model
model = ChatOpenAI(model="gpt-4o", temperature = 0.8)
task_verifier_model = ChatOpenAI(model="gpt-4o", temperature = 0.5)
refactor_model = ChatOpenAI(model="gpt-4o", temperature = 0.2)

# load adl
adl = load_adl(adl_file_name)

global current_ADL, current_understanding, current_properties, refactored_ADL, refactored_understanding, refactored_properties, final_verification, post_process, task_verified, Final_VV_result
current_ADL = adl
current_understanding = ""
current_properties = ""
refactored_ADL = ""
refactored_understanding = ""
refactored_properties = ""
final_verification = ""
post_process = ""
task_verified = ""
Final_VV_result = ""

global memory_leader_refactoring
memory_leader_refactoring = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

def store_subtasks_from_response(response: str, store, namespace: tuple):
    """
    Extracts sub-tasks from the given response text, creates Task objects,
    and stores them in the given store under the provided namespace.
    
    Parameters:
        response (str): The full textual response containing sub-tasks.
        store: An object that supports put(namespace, key, value) for storing tasks.
        namespace (tuple): The namespace used for storing tasks.
    """
    # Regex pattern to capture sub-task sections
    pattern = r"Sub-task\s+\d+:\s*(.+?)(?=\nSub-task|\n\n|\Z)"
    matches = re.findall(pattern, response, flags=re.DOTALL)

    # find each extracted sub-task description,then Create and store each sub-task
    for match in matches:
        sub_task_desc = match.strip()
        if sub_task_desc:
           sub_task = Task(
            description=sub_task_desc,
            status="not started",
            feedback_status="not started",
            feedback=""
        )
        store.put(namespace, sub_task.task_id, sub_task.dict())


def extract_context_from_response(context: str, response: str):
    pattern = re.escape(context) + r"\s*\n\s*(.*?)(?:\n[A-Z]|$)"
    match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
    if match:
        extracted_info = match.group(1).strip()
        return extracted_info

def extract_code(response:str):
    """
    Extracts Python code lines that start with 'wright_code =' from raw text.

    :param text: Raw text containing Python code.
    :return: List of extracted Python code lines.
    """

    # Regex pattern to match lines that start with 'wright_code ='
    pattern = r"^\s*wright_code\s*=.*"

    # Find all matching lines in the text
    matches = re.findall(pattern, response, re.MULTILINE)

    return '\n'.join(matches)  # Clean up whitespace

# Define the Task schema
class Task(BaseModel):
    task_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique identifier for the task",
    )
    description: str = Field(description="Description of the task to be completed")
    
    status: Literal["not started", "in progress", "completed"] = Field(
        default="not started", description="Current status of the task"
    )
    result: Optional[str] = Field(
        default=None, description="Result of the task after completion"
    )
    feedback_status:  Literal["not started", "Approved", "Rejected"] = Field(
        default="not started", description="Whether the Architect_Leader agree with the new design"
    )
    feedback: Optional[str] = Field(
        default="", description="Whether feedback has been given for the task"
    )
    verification_status:  Literal["not started", "Valid", "Invalid", "Error"] = Field(
        default="not started", description="Whether the Architect_Leader agree with the new design"
    )
    verification_results: Optional[list] = Field(
        default=[], description="Whether feedback has been given for the task"
    )

# Create LLMChain agents
# Architect_Leader agent chain
def create_Architect_Leader_agent():
    global memory_leader_refactoring
    system_prompt = """
    You are an expert in software architecture and formal modeling, specializing in Wright# ADL.
    Your task is to analyze the given Wright# ADL system definition and modify it based on a new requirement.
    Also, give feedback for the refactored ADL.
    """
    prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessagePromptTemplate.from_template(system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            HumanMessagePromptTemplate.from_template("{input_text}"),
        ]
    )
    memory = memory_leader_refactoring
    chain = LLMChain(llm=model, prompt=prompt, memory=memory)
    return chain

#
def create_taskverfier_agent():
    system_prompt = """You are a subtasks reviewer, Output exactly in the defined format!"""
    prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessagePromptTemplate.from_template(system_prompt),
            HumanMessagePromptTemplate.from_template("{input_text}"),
        ]
    )
    chain = LLMChain(llm=task_verifier_model, prompt=prompt)
    return chain

# Verifier chain
def create_verfier_agent():
    system_prompt = """You are a software architecture verification agent to verify liveness properties based on new requirement."""
    prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessagePromptTemplate.from_template(system_prompt),
            HumanMessagePromptTemplate.from_template("{input_text}"),
        ]
    )
    chain = LLMChain(llm=model, prompt=prompt)
    return chain

def create_refactoring_agent():
    global memory_leader_refactoring
    system_prompt = """You are an refactoring expert in generating the python codes for refactoring."""
    prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessagePromptTemplate.from_template(system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            HumanMessagePromptTemplate.from_template("{input_text}"),
        ]
    )
    memory = memory_leader_refactoring
    chain = LLMChain(llm=refactor_model, prompt=prompt, memory=memory)
    return chain

def get_response_deepseekr1_postprocessing(user_content):
    client = OpenAI(api_key="YOUR_DEEPSEEK_API_KEY", base_url="https://api.deepseek.com")

    response = client.chat.completions.create(
        model="deepseek-reasoner",
        messages=[
            {"role": "system", "content": """You are an expert system architect. Your job is to fix **illegal design** in a set of **attach statements**. 
            Illegal case: A design is **illegal** if the **same input role** of a connector is attached to **multiple component ports**.
            ONLY Output the final fixed design.
            """},
            {"role": "user", "content": user_content},
        ],
        stream=False
    )
    return response.choices[0].message.content


# Initialize agents
Architect_Leader_agent_chain = create_Architect_Leader_agent()
verfier_agent_chain = create_verfier_agent()
refactoring_agent_chain = create_refactoring_agent()
taskverfier_agent_chain = create_taskverfier_agent()
def Architect_Leader_agent(state: MessagesState, config: RunnableConfig, store: BaseStore):
    """
    Architect_Leader agent receives the main task, analyzes it, splits it into sub-tasks,
    and provides feedback on task executor solutions.
    """
    global memory_leader_refactoring
    global current_ADL, current_understanding, current_properties, refactored_ADL, refactored_understanding, refactored_properties, task_verified
    # Check if the Architect_Leader has already split the tasks, if not create subtasks, and store with namespace('tasks, old tasks')
    if task_verified == "":
        user_id = "old tasks"
        namespace = ("tasks", user_id)
    else:
        user_id = config.get("configurable", {}).get("user_id", "default_user")
        namespace = ("tasks", user_id)
    tasks = store.search(namespace, limit = 100)

    if not tasks:
        # First interaction: the Architect_Leader needs to analyze and split the main task
        # Get the main task from the user message
        user_messages = [
            msg for msg in state["messages"] if isinstance(msg, HumanMessage)
        ]
        if user_messages:
            main_task = user_messages[-1].content

            # #store paths to string
            formatted_paths = get_extended_paths_with_connector_info(adl_file_name)
            # Architect_Leader analyzes and splits the main task using the chain
            input_text = f"""
            Step by Step to output the sub-tasks for refactor the provided ADL based on the new requirement.
            ### **Step 1: Understand the Current ADL System (Structural and Behavioral Analysis) by reading the provided details information** 
                        - no output required for this step, you just need to understand them.
                        - understand the components, ports, events. As for each port, it is in the format: port port_name() = event -> port_name()
                        - understand connector variables and their type, and especially their roles. Connector types and roles are defined in Connector Block. Connector Variables are declared in System Block by "declare connector_variable_name connector_type;".
                        - understand the system interations defined by attach statements, the attach statements are in format: attach component.port = connector.role <*> ... <*> connector.role. The left hand side of '=' is component.port, the right hand side of '=' is connector.role.
                        - <*> refers to Coupling process, it specifies the order of the attached connector roles. For example: connector.roleA <*> connector.roleB, will go to connector.roleA, after it done, it goes to connector.roleB.
            
            ### **Step 2: Comprehend the Provided New Requirement and determine the new paths step by step and ** following the Key rules listed below**
                        ### Key Rules for Designing Attachments by refering to avaiable attach from Step 1:
                        - **Rule 1 for creating a new port: 
                            - ENSURE each port has its unique name, when creating a new port, need to have a distinct name from the existing ports, even they are in different component.
                            - ENSURE the event has a different name to its own port
                        
                        - **Rule2: Do not create new connector type, but you can delcare new connector variables.
                        
                        - **Analyze Existing Path Workflows and avaiable attach:** Carefully review existing system paths. **You can reuse any existing paths**
                        - **Based on the requirement, Identify all new **Components** and **ports** and reuse existing ones where applicable by **strictly following the Key Rules** listed above.       
                        - **Determine and Generate New Paths to achieve the new requirement by **strictly following the Key rules listed above** and ** list the new paths.
            
            ### **Step 3: Based on the new paths from Step 2, plan the modifications step by step**
                    1. **Identify All Required Structural Changes to achieve the new paths:**  
                      - Determine if the new paths requires **adding**, **modifying**, or **removing**:  
                        - **Components** and **ports**  
                        - **Connectors**
                            - Do not define new Connector type or add role to an existing Connnector type, but you can declare new Connector Variables
 
                    2. **Update all necessary **attach statements** to reflect the new interations required for the new paths**  
                      - ENSURE each role in a connector variable (especially new connectors) is attached to a port for maintain correct data flow.
                      - ENSURE No Port-to-Port Direct Attachments:** Use a connector.role between ports, even within the same component.
                      
                    
            ### **Final Step: Output Specific Modification Actions on given ADL (No Verification Needed) as Sub-Tasks**
                    - Break down the changes into detailed and specific actions
                    - ENSURE each role in a connector variable (especially the connector variable is declared as a three-role connector type like ESConnector) is attached to a port for maintain correct data flow.
                    - List all modification actions clearly and concisely as sub-tasks.  
                    - The sub-tasks should **only contain specific modification steps** in the **following format**.  
                        Sub-task 1: [Sub-task description]
                        Sub-task 2: [Sub-task description]
                        Sub-task 3: [Sub-task description]
            Please ensure that the sub-task descriptions do not contain additional numbering or labels.
            
            ADL:\n{adl}
            New requirement:  {new_requirement}
            Here is the existing paths of current ADL:\n {formatted_paths}
            """
            response = Architect_Leader_agent_chain.predict(input_text=input_text)
            # extract and store current_understanding from response

            # store the conversations to messagesstate
            AI_messages = [AIMessage(content=response)]

            store_subtasks_from_response(response, store, namespace)
            return {"messages": AI_messages}

    # generate feedback based on the refactored ADL or verification results
    if tasks:
        for item in tasks:
            t_dict = item.value
            task = Task(**t_dict)
            # if refactoring is not started, then go to route and start refactoring
            if task.status == "not started":
                AI_messages = [AIMessage(content="Subtasks are confirmed! Refactoring starts now!")]
                return {"messages": AI_messages}
            # refactoring started, awaiting for feedback from leader, verificaton for this task is not started
            if task.status == "in progress" and task.feedback_status!= "Approved":
                input_text = (f"""
                    Please give feedback to the refactored ADL step by step:\n{refactored_ADL}
                    Are you agree with the refactored ADL based on the sub task: {task.description}
                    ### **Review Guidelines**
                    ONLY focus on **if the specific sub task is completed**.
                    - **Ignore** aspects that are **not part of this sub-task** (e.g., ignore connectors if the sub-task is about components).
                    - **Do not care about the consistency or readability or overloading**
                    - ** Its absolutely fine to use existing workflows!**
                    If yes, just output 'Approved!', if not, output 'Rejected!' and then list the reasons and refined steps in following format:
                    Rejected!
                    Please ensure that the Rejected reasons do not contain additional numbering or labels.""")
                response = Architect_Leader_agent_chain.predict(input_text=input_text)
                memory_leader_refactoring.chat_memory.messages.pop(-1)
                memory_leader_refactoring.chat_memory.messages.pop(-1)
                
                # extract and store current_understanding from response
                refactored_understanding = extract_context_from_response("Understanding from Architect leader of current system:", response)
                
                if extract_context_from_response("Rejected!", response) == None:
                    item.value['feedback_status'] = "Approved"
                    item.value['status'] = "completed"
                    current_ADL = refactored_ADL
                    current_understanding = refactored_understanding
                    current_properties = refactored_properties
                    AI_messages = [AIMessage(content=f"\nApproved, current updated ADL is: {refactored_ADL}, please continue to the next subtask")]
                    # memory_leader_refactoring.chat_memory.add_user_message(f"Approved, current updated ADL is: {refactored_ADL}, please continue to the next subtask")
                else:
                    item.value['feedback_status'] = "Rejected"
                    item.value['feedback'] = response
                    # store the conversations to messagesstate
                    AI_messages = [AIMessage(content=response)]
                
                return {"messages": AI_messages}

            # if verification failed, leader need to update feedback with the verification results
            if task.status == "in progress" and task.feedback_status == "Approved" and task.verification_status == "Invalid":
                item.value['feedback_status'] = "not started"
                input_text = (
                    f"Analyze and understand the following ADL:\n{refactored_ADL}, Please provide your refactoing suggestion of the system based on {task.description} and {task.verification_results} in the following format starting with words:\n"
                    "refactoring suggestion from Architect leader of current system:\n"
                    "Please ensure that the refactoring suggestion do not contain additional numbering or labels.\n")
                response = Architect_Leader_agent_chain.predict(input_text=input_text)
                item.value['feedback'] = extract_context_from_response("refactoring suggestion from Architect leader of current system:", response)
                
                # store the conversations to messagesstate
                AI_messages = [AIMessage(content=response)]
                return {"messages": AI_messages}
                
def taskverifier_agent(state: MessagesState, config: RunnableConfig, store: BaseStore):
    global current_ADL, current_understanding, current_properties, refactored_ADL, refactored_understanding, refactored_properties, task_verified
    subtasks = ""
    i = 1
    # retrieve sub tasks which are not verified
    user_id = "old tasks"
    namespace = ("tasks", user_id)
    tasks = store.search(namespace, limit = 100)
    for item in tasks:
        t_dict = item.value
        task = Task(**t_dict)
        subtasks += f"Sub-task{i}: {task.description}\n"
        i = i+1

    input_text = f"""
    Analyze the provided ADL and Subtasks by following this process step by step and Output in the certion format:
    1. Identify Components and Ports:
        - Analyze the ADL to understand all components and their ports.
    
    2. Identify Connector Variables and Types:
        - Identify declared connector variables in the System Block (e.g., declare connector_variable_name connector_type;).
        - Understand the connector types and roles from the Connector Block.

    3. Identify Roles for Each Connector Variable:
        - By referring to connector variable declarations and connector type definitions, Identify the roles associated with each connector variable.

    4. Review the Given Subtasks:
        - Analyze the provided subtasks to understand their intent and how they modify the system.

    5. Validate Attachment of Connector Roles of new Connector Variable:
        5.1 For each new connector variable introduced in the subtasks, check whether each role of the new connector variable is properly attached to a component port.
        5.2 If a connector role is unattached, attach the connector role to a component.port:
            - If a suitable port exists: Modify the subtasks list by adding a subtask to attach the role to the port.
            - If no suitable port exists: Create a new port on an existing component OR a new component with a port to ensure logical system integration for {new_requirement}. Modify the subtasks list by adding the new component.port and attaching the unattached role to the new component.port.
    6. Repeat Step 5 for All New Connector Variables.
    
    Expected Output in the following format:
    1. If all connector roles are properly attached to a component's port, Output the word "Correct!" only, with no extra content.
    2. If not, Output the full list of subtasks (original + new subtasks) in the format below:  
       Sub-task 1: [Sub-task description]
       Sub-task 2: [Sub-task description]
       Sub-task 3: [Sub-task description]

     ADL Specification:\n{adl}
     Subtasks:\n{subtasks}

    """
    response = taskverfier_agent_chain.predict(input_text=input_text)

    # store the verified subtasks with namespace('tasks', "default_user")
    user_id = config.get("configurable", {}).get("user_id", "default_user")
    namespace = ("tasks", user_id)
    
    if "Correct!" in response:
        store_subtasks_from_response(subtasks, store, namespace)
        AI_messages = [AIMessage(content="Sub-tasks are correct!")]
    else:
        store_subtasks_from_response(response, store, namespace)
        AI_messages = [AIMessage(content=response)]
        
    task_verified = "Verified!"
    return {"messages": AI_messages}


def verify_each_portion_of_the_adl(adl: str) -> str:
    """Verify each portion of the entire software architecture design in adl

    Args:
        adl: the entire adl of the whole software architecture design
    """
    return get_verification_results_with_adl

def verifier_agent(state: MessagesState, config: RunnableConfig, store: BaseStore):
    global current_ADL, current_understanding, current_properties, refactored_ADL, refactored_understanding, refactored_properties, final_verification, Final_VV_result
    # Verification
    final_verification = "checked"
    Final_VV_result = "checked"  
    
    AI_messages = [AIMessage(content=Final_VV_result)]
    return {"messages": AI_messages}

def refactoring_agent(state: MessagesState, config: RunnableConfig, store: BaseStore):
    global current_ADL, current_understanding, current_properties, refactored_ADL, refactored_understanding, refactored_properties, wright_code
    global memory_leader_refactoring
    # retrieve the first task whose progress is "not started" or " in progress"
    user_id = config.get("configurable", {}).get("user_id", "default_user")
    namespace = ("tasks", user_id)
    tasks = store.search(namespace, limit = 100)
    for item in tasks:
        t_dict = item.value
        task = Task(**t_dict)
        # Refactoring
        if task.status == "not started":
            input_text = f"""
            Based on the current Wright ADL of software architecture design:\n{current_ADL},\n the understanding of the design, and refactored plan generated by Architect leader: {task.description}\n
            Pay Attention to the Following Points:
            1. Make sure the each port in components are connected to a role of a connector.
            2. Do not define a new connector type, using existing type of connectors like CSConnector, WRConnector
            3. Generate the python codes for refactoring, make sure you list the python function calls with correct parameters from the following list.
            4. If the thing you want to add is already in the system, just skip adding the thing\n
            Available Python Function Calls:\n
            1. add_port_to_component(wright_code, component_name, port_name, process_sequence)
            2. add_component(wright_code, component_name)
            3. delete_port_from_component(wright_code, component_name, port_name)
            4. delete_component(wright_code, component_name)
            5. add_role_to_connector(wright_code, connector_name, role_name, process_sequence)
            6. add_connector(wright_code, connector_name)
            7. delete_role_from_connector(wright_code, connector_name, role_name)
            8. delete_connector(wright_code, connector_name)
            9. add_attachment(wright_code, component_name, port_name, connector_name, role_name, parameters=None)
            10. delete_attachment(wright_code, component_name, port_name, connector_name, role_name)
            11. add_declare_connector(wright_code, connector_name, connector_type)
            12. delete_declare_connector(wright_code, connector_name)
            13. add_execute_component(wright_code, component_name, port_name
            14. delete_execute_component(wright_code, component_name, port_name)

            Output the python codes:\n
            Please ensure that the python codes do not contain any title, or explination, or additional empty line, numbering or labels.\n
            Example Output:
            wright_code = add_component(wright_code, "FoodUI")
            wright_code = add_port_to_component(wright_code, "FoodUI", "placeOrder", "place->placeOrder()")
            wright_code = delete_declare_connector(wright_code, "foodwire")
            wright_code = add_declare_connector(wright_code, "foodwire", "CSConnector")
            wright_code = add_attachment(wright_code, "FoodUI", "placeOrder", "foodwire", "requester", "11")
            wright_code = add_attachment(wright_code, "FoodMgmt", "acceptOrder", "foodwire", "responder", None)
            wright_code = delete_attachment(wright_code, "FoodMgmt", "acceptOrder", "foodwire", "responder")
            wright_code = add_execute_component(wright_code, "FoodUI", "placeOrder")
            wright_code = delete_execute_component(wright_code, "FoodUI", "placeOrder")
            """
            response = refactoring_agent_chain.predict(input_text=input_text)
            wright_code = current_ADL
            exec(extract_code(response), globals())
            refactored_ADL = wright_code
        
            # update tasks and global variables
            item.value['status'] = "in progress"
            memory_leader_refactoring.chat_memory.messages.pop(-1)
            memory_leader_refactoring.chat_memory.messages.pop(-1)
            AI_messages = [AIMessage(content=f"refactored_ADL:{refactored_ADL}")]
            return {"messages": AI_messages}
            
        # refining
        if task.status == "in progress":
            input_text = f"""
            Based on the feedback from Architect leader: {task.feedback}, you need to further refine the refactored ADL:\n {refactored_ADL}
            Pay Attention to the Following Points:
            1. Make sure the each port in components are connected to a role of a connector.
            2. Do not define a new connector type, using existing type of connectors like CSConnector, WRConnector
            3. Generate the python codes for refactoring, make sure you list the python function calls with correct parameters from the following list.
            4. If the thing you want to add is already in the system, just skip adding the thing\n
            Available Python Function Calls:\n
            1. add_port_to_component(wright_code, component_name, port_name, process_sequence)
            2. add_component(wright_code, component_name)
            3. delete_port_from_component(wright_code, component_name, port_name)
            4. delete_component(wright_code, component_name)
            5. add_role_to_connector(wright_code, connector_name, role_name, process_sequence)
            6. add_connector(wright_code, connector_name)
            7. delete_role_from_connector(wright_code, connector_name, role_name)
            8. delete_connector(wright_code, connector_name)
            9. add_attachment(wright_code, component_name, port_name, connector_name, role_name, parameters=None)
            10. delete_attachment(wright_code, component_name, port_name, connector_name, role_name)
            11. add_declare_connector(wright_code, connector_name, connector_type)
            12. delete_declare_connector(wright_code, connector_name)
            13. add_execute_component(wright_code, component_name, port_name
            14. delete_execute_component(wright_code, component_name, port_name)

            Output the python codes:\n
            Please ensure that the python codes do not contain any title, or explination, or additional empty line, numbering or labels.\n
            Example Output:
            wright_code = add_component(wright_code, "FoodUI")
            wright_code = add_port_to_component(wright_code, "FoodUI", "placeOrder", "place->placeOrder()")
            wright_code = delete_declare_connector(wright_code, "foodwire")
            wright_code = add_declare_connector(wright_code, "foodwire", "CSConnector")
            wright_code = add_attachment(wright_code, "FoodUI", "placeOrder", "foodwire", "requester", "11")
            wright_code = add_attachment(wright_code, "FoodMgmt", "acceptOrder", "foodwire", "responder", None)
            wright_code = delete_attachment(wright_code, "FoodMgmt", "acceptOrder", "foodwire", "responder")
            wright_code = add_execute_component(wright_code, "FoodUI", "placeOrder")
            wright_code = delete_execute_component(wright_code, "FoodUI", "placeOrder")
            """
            response = refactoring_agent_chain.predict(input_text=input_text)
            # update tasks and global variables
            wright_code = refactored_ADL
            exec(extract_code(response), globals())
            refactored_ADL = wright_code

            memory_leader_refactoring.chat_memory.messages.pop(-1)
            memory_leader_refactoring.chat_memory.messages.pop(-1)
            AI_messages = [AIMessage(content=f"refactored_ADL:{refactored_ADL}")]
            return {"messages": AI_messages}

def postprocessing_agent(state: MessagesState, config: RunnableConfig, store: BaseStore):
    global current_ADL, current_understanding, current_properties, refactored_ADL, refactored_understanding, refactored_properties, post_process

    print(current_ADL)
    
    # identify illegal design patterns for the first issue: a input role is connected to multiple ports
    connector_roles = extract_connector_order(current_ADL)
    issues, matching_attachment_CIR, matching_attachment_COR = detect_output_role_issues(extract_attach_statements(current_ADL), connector_roles)
    if issues:
        # 1st issue detected,
        # Call deepseek r1 to fix it
        illegal_pattern =  matching_attachment_CIR + matching_attachment_COR
        # get rid of duplicates
        illegal_pattern = list(set(illegal_pattern))
        illegal_pattern_string = "\n".join(illegal_pattern)
        question = f"""
            As for the illegal design: the same input role of a connector is attached to multiple component ports.
            To fix the illegal design, follow these steps:
                
            1. Read the Connector details, know different connector type, and their output role and input roles, all the information is provided by Connector details.
            Here is the Connector details:  
            the first column is the the connector type, the second column is the output role, and the third column is the first input role, and the fourth is the second input role.
            {connector_roles}
                
            2. Preserve the Most Contextually Appropriate Attachment:
                - Choose the attachment that represents the **primary data flow**.
                - This is typically the one that:
                    - Has the most **complex chain** (e.g., has multiple <*> hops).
                    - Connects to **core components** or **critical system flows**.
                - Redirect simpler attachments over complex ones.
                
            3. Splitting Connectors:  
                - Create a **new connector** in the same type but with a new name for the conflicting attachments.
                - Write the Delaration for the new connector in the format: declare new_connector_name = connector_type, for example, declare testwire = WRConnector;
                - Modify simpler illegal attachment by replacing the original connector's input role with the new connector's input role.
                - Locate the attachment which the corresponding original connector's output role is connected. Then extend the attachment with the new connector's output role with new parameter by using coupling sign <*>. The correct format of **the new connector's output role with new parameter**: new_connector_name.outputrole(parameter) 
                
            4. After you get the correct design:
                - check if there is still some illegal design that the same input role of a connector is attached to multiple component ports. If so, do the fixing process again. If not, just output the final fixed design (new declaration + attachments).
                
            5. Final Output: ONLY Output the final fixed design(new declaration + attachments)
                
            Now you need to fix the illegel design:
            {illegal_pattern_string}
            *** ONLY Output the final fixed design(new declaration + attachments) ***
            """
        response = get_response_deepseekr1_postprocessing(question)
        print(response)
        # update refactored ADL with new attachments
        new_attachments = response.split("\n")
        current_ADL = replace_attachments_in_adl(current_ADL, illegal_pattern, new_attachments)
              
    # use the postprocessing python to fix the second issue: same port is attached to multiple input roles.    
    current_ADL = fix_same_port_multiple_input_roles(current_ADL)

    # remove parameters from input roles, this could lead to syntax error
    current_ADL = remove_parameters_from_input_roles(current_ADL)

    # ensure the parameters of output roles are number
    current_ADL = ensure_parameters_correct_output_roles(current_ADL)

    # make sure every component and port are defined
    current_ADL = extract_fix_undefined_component_port(current_ADL)

    # make sure the input roles are in front of output roles when using coupling, make sure behaviour consistency
    current_ADL = reorder_input_roles_first(current_ADL)

    # secure_execution
    current_ADL = secure_execution(current_ADL)
    
    # after fix it, update
    post_process = "Completed"
    print(current_ADL)
    AI_messages = [AIMessage(content=f"Final Refactored ADL with no illegal patterns:\n {current_ADL}")]
    return {"messages": AI_messages}

def route_message(state: MessagesState, config: RunnableConfig, store: BaseStore) -> Literal[END, "verifier_agent", "refactoring_agent", "postprocessing_agent", "taskverifier_agent"]:
    global current_ADL, current_understanding, current_properties, refactored_ADL, refactored_understanding, refactored_properties, final_verification, post_process, task_verified

    if task_verified == "":
        return "taskverifier_agent"
    
    if final_verification != "":
        return END

    # if not the first run, it routes to verifier agent or refactored agent.
    # this means, either refactoring not started, refactoring started but feedback is rejected, refactoring started and feedback is approved.
    else:
        # check the status of tasks
        user_id = config.get("configurable", {}).get("user_id", "default_user")
        namespace = ("tasks", user_id)
        tasks = store.search(namespace, limit = 100)
        for item in tasks:
            t_dict = item.value
            task = Task(**t_dict)
            # the only possible way to verifier agent, is the refactored ADL is presented and approved, but the task is still in progress,
            # since properties are not generated.
            if task.status == "in progress" and task.feedback_status == "Approved":
                return "verifier_agent"
        # check if all tasks are completed, now either goes to refactoring agent, or END
        for item in tasks:
            t_dict = item.value
            task = Task(**t_dict)
            if task.status != "completed":
                return "refactoring_agent"

        # do the post processing before getting the final refactored ADL passing to the verifier
        if post_process == "":
            return "postprocessing_agent"
            
        return "verifier_agent"

# Build the StateGraph
builder = StateGraph(MessagesState)

# Add nodes using the uniquely named functions
builder.add_node(Architect_Leader_agent)
builder.add_node(verifier_agent)
builder.add_node(taskverifier_agent)
builder.add_node(refactoring_agent)
builder.add_node(postprocessing_agent)

# Add edges
builder.add_edge(START, "Architect_Leader_agent")
builder.add_conditional_edges("Architect_Leader_agent", route_message)
builder.add_edge("verifier_agent", "Architect_Leader_agent")
builder.add_edge("taskverifier_agent", "Architect_Leader_agent")
builder.add_edge("refactoring_agent", "Architect_Leader_agent")
builder.add_edge("postprocessing_agent", "Architect_Leader_agent")

# Compile the graph
store = InMemoryStore()
graph = builder.compile(store=store)

# Configuration
user_id = "Jeffrey"
config = {"configurable": {"thread_id": "1", "user_id": user_id}}

# User input messages
input_messages = [
    HumanMessage(
        content="""Analyze an existing software architecture and a new requirement to incorporate a new requirement 
                    while preserving its modularity and alignment with the original architecture."""
    )
]

# Run the graph
state = {"messages": input_messages}
config = RunnableConfig(recursion_limit=50)
for chunk in graph.stream(state, config=config, stream_mode="values"):
    # Update the state with each chunk
    state.update(chunk)
    # chunk["messages"][-1].pretty_print()


