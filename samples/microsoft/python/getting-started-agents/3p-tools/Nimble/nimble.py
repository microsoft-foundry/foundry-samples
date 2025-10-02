# pylint: disable=line-too-long,useless-suppression
# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

"""
DESCRIPTION:
    This sample demonstrates how to use the Nimble APIs (Web Search and Maps) 
    with the Azure AI Foundry Agent Service.

USAGE:
    python nimble.py

    Before running the sample:

    pip install azure-ai-agents azure-identity jsonref

    Set these environment variables with your own values:
    1) PROJECT_ENDPOINT - the Azure AI Agents endpoint.
    2) MODEL - The deployment name of the AI model, as found under the "Name" column in
       the "Models + endpoints" tab in your Azure AI Foundry project.
    3) CONNECTION_ID - The connection ID for your custom key connection.
"""
# <initialization>
# Import necessary libraries
import os
import jsonref
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import OpenApiTool, OpenApiConnectionAuthDetails, OpenApiConnectionSecurityScheme

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
    with open("./nimble.json", "r") as f:
        openapi_spec = jsonref.loads(f.read())

    # Create Auth object for the OpenApiTool (connection auth setup requires additional setup in Azure)
    auth = OpenApiConnectionAuthDetails(security_scheme=OpenApiConnectionSecurityScheme(connection_id=conn_id))

    # Initialize the main OpenAPI tool definition for Nimble
    openapi_tool = OpenApiTool(
        name="nimble", 
        spec=openapi_spec, 
        description="Search the web and retrieve maps data using Nimble APIs", 
        auth=auth
    )

    # <agent_creation>
    # --- Agent Creation ---
    # Create an agent configured with the Nimble OpenAPI tool
    agent = project_client.agents.create_agent(
        model=model, # Specify the model deployment
        name="nimble-agent", # Give the agent a name
        instructions="You are a helpful assistant with access to web search and maps data through Nimble. For web searches, use the nimbleDeepWebSearch operation. For maps data, use the googleMapsOperations operation with the appropriate search_engine parameter (google_maps_search, google_maps_place, or google_maps_reviews).", # Define agent's role
        tools=openapi_tool.definitions, # Provide the list of tool definitions
    )
    print(f"Created agent, ID: {agent.id}")
    # </agent_creation>

    # <thread_management>
    # --- Thread Management ---
    # Create a new conversation thread for the interaction
    thread = project_client.agents.threads.create()
    print(f"Created thread, ID: {thread.id}")

    # Create the initial user message in the thread
    message = project_client.agents.messages.create(
        thread_id=thread.id,
        role="user",
        # give an example of a user message that the agent can respond to
        content="Find information about machine learning and then show me popular coffee shops in San Francisco",
    )
    print(f"Created message, ID: {message.id}")
    # </thread_management>

    # <message_processing>
    # --- Message Processing (Run Creation and Auto-processing) ---
    # Create and automatically process the run, handling tool calls internally
    run = project_client.agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
    print(f"Run finished with status: {run.status}")
    # </message_processing>

    # <tool_execution_loop>
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
    print(f"Messages: {messages}")
    # </cleanup>
