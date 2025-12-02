# pylint: disable=line-too-long,useless-suppression
# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

"""
DESCRIPTION:
    This sample demonstrates how to use agent operations with the 
    OpenAPI tool from the Azure Agents service using a synchronous client.
    To learn more about OpenAPI specs, visit https://learn.microsoft.com/openapi

USAGE:
    python insureMO_Quotation.py

    Before running the sample:

    pip install azure-ai-agents azure-identity jsonref azure-ai-projects

    Set these environment variables with your own values:
    1) PROJECT_ENDPOINT - the Azure AI Agents endpoint.
    2) MODEL - The deployment name of the AI model, as found under the "Name" column in
       the "Models + endpoints" tab in your Azure AI Foundry project.
    3) CONNECTION_ID - The connection ID for the OpenAPI tool, which can be found in the Azure portal.
"""
# <initialization>
# Import necessary libraries
import os
import jsonref
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import OpenApiTool, OpenApiConnectionAuthDetails, OpenApiConnectionSecurityScheme
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# endpoint should be in the format "https://<your-ai-services-resource-name>.services.ai.azure.com/api/projects/<your-project-name>"
endpoint = os.environ["PROJECT_ENDPOINT"]
model = os.environ["MODEL"]
# connection id should be in the format "/subscriptions/<sub-id>/resourceGroups/<your-rg-name>/providers/Microsoft.CognitiveServices/accounts/<your-ai-services-name>/projects/<your-project-name>/connections/<your-connection-name>"
conn_id = os.environ["CONNECTION_ID"]

# Initialize the project client using the endpoint and default credentials
with AIProjectClient(
    endpoint=endpoint,
    credential=DefaultAzureCredential(exclude_interactive_browser_credential=False),
) as project_client:
    # </initialization>

    # Load the OpenAPI specification for the service from a local JSON file using jsonref to handle references
    with open("./insuremo_openapi_spec.json", "r") as f:
        openapi_spec = jsonref.loads(f.read())

    # Create Auth object for the OpenApiTool (note that connection or managed identity auth setup requires additional setup in Azure)
    auth = OpenApiConnectionAuthDetails(security_scheme=OpenApiConnectionSecurityScheme(connection_id=conn_id))

    # Initialize the main OpenAPI tool definition for Insurance Quotation
    openapi_tool = OpenApiTool(
        name="InsuerMOQuotation", 
        spec=openapi_spec, 
        description="generate insurance quotations", 
        auth=auth
    )

    # <agent_creation>
    # --- Agent Creation ---
    # Create an agent configured with the combined OpenAPI tool definitions
    agent = project_client.agents.create_agent(
        model=model, # Specify the model deployment
        name="my-agent", # Give the agent a name
        instructions="You are a helpful insurance agent, help the user with their insurance quotation.", # Define agent's role
        tools=openapi_tool.definitions, # Provide the list of tool definitions
    )
    print(f"Created agent, ID: {agent.id}")
    # </agent_creation>

    # <thread_management>
    # --- Thread Management ---
    # Create a new conversation thread for the interaction
    thread = project_client.agents.threads.create()
    print(f"Created thread, ID: {thread.id}")

    # user input for car insurance quotation
    user_input_car = "Please get me a car insurance quotation for a policy effective from May 1, 2025 to April 30, 2027 for a 30-year-old driver named John Doe " \
    "(driver’s license number ABC123456, expiring December 31, 2028). The quotation should include Own Damage Basic, Personal Accident to Owner/Driver, " \
    "Third-Party Liability, and Third-Party Property Damage coverages. The vehicle is a 2020 Honda Civic EX sedan with a market value of 250,000, petrol fuel, " \
    "a 2000 cc engine capacity, licensed to carry five passengers, chassis number 1HGCM82633A004352, engine number K20A31122334, and registration number XYZ789"

    # user input for home insurance quotation
    user_input_home = "Please get me a home insurance quotation for a policy effective from May 1, 2025 to May 1, 2026 for a one-year-old, "\
    "tile-constructed Building Type 1 with a built-up and total area of 2,222 sq ft. The coverages should include alternate accommodation "\
    "(rental limit ₹50,010), keys and locks replacement, contents in storage, legal liability as owner, and tenants’ legal liability. "\
    " The total value of specified contents is ₹12,000 and the property is insured for a sum of ₹12,000"

    # user input for travel insurance quotation
    user_input_travel = "Please get me a travel insurance quotation for a policy effective from April 29, 2025 to May 15, 2026 covering travel to India for 20 people, " \
    "including a 35-year-old male named John Doe. The trip is scheduled from May 1, 2025 to May 15, 2026. Include trip cancellation cover with a ₹20,000 limit, " \
    "flight delay cover with a ₹20,000 limit, trip delay cover with a ₹20,000 limit, loss of checked baggage cover up to ₹20,000, delay of checked baggage cover " \
    "up to ₹20,000, accidental death cover with a ₹20,000 limit, personal liability benefit excess of ₹200, and legal liability cover where applicable. The proposer " \
    "has not previously declined insurance and has no claims history."

    # Create the initial user message in the thread
    message = project_client.agents.messages.create(
        thread_id=thread.id,
        role="user",
        # give an example of a user message that the agent can respond to
        content=user_input_car, # Change this to user_input_home or user_input_travel to test other inputs
    )
    print(f"Created message, ID: {message.id}")
    # </thread_management>

    # <message_processing>
    # --- Message Processing (Run Creation and Auto-processing) ---
    # Create and automatically process the run, handling tool calls internally
    # Note: This differs from the function_tool example where tool calls are handled manually
    run = project_client.agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
    print(f"Run finished with status: {run.status}")
    # </message_processing>

    # <tool_execution_loop> # Note: This section now processes completed steps, as create_and_process_run handles execution
    # --- Post-Run Step Analysis ---
    if run.status == "failed":
        print(f"Run failed: {run.last_error}")

    # Retrieve the steps taken during the run for analysis
    run_steps = project_client.agents.run_steps.list(thread_id=thread.id, run_id=run.id)

    # Loop through each step to display information
    for step in run_steps:
        print(f"Step {step['id']} status: {step['status']}")

        # Check if there are tool calls recorded in the step details
        step_details = step.get("step_details", {})
        tool_calls = step_details.get("tool_calls", [])

        if tool_calls:
            print("  Tool calls:")
            for call in tool_calls:
                print(f"    Tool Call ID: {call.get('id')}")
                print(f"    Type: {call.get('type')}")

                function_details = call.get("function", {})
                if function_details:
                    print(f"    Function name: {function_details.get('name')}")
        print() # Add an extra newline between steps for readability
    # </tool_execution_loop>

    # <cleanup>
    # --- Cleanup ---
    # Delete the agent resource to clean up
    project_client.agents.delete_agent(agent.id)
    print("Deleted agent")

    # Fetch and log all messages exchanged during the conversation thread
    messages = project_client.agents.messages.list(thread_id=thread.id)
    for message in messages:
        print(f"Message ID: {message.id}, Role: {message.role}, Content: {message.content}")
        
    # </cleanup>