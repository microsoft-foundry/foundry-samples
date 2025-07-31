# pylint: disable=line-too-long,useless-suppression
# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

"""
DESCRIPTION:
    This sample demonstrates how to use agent operations with the
    LexisNexis OpenAPI tool, from the Azure Agents service using a synchronous client.
    To learn more about OpenAPI specs, visit https://learn.microsoft.com/openapi

USAGE:
    python web_services_api_agent.py

    Before running the sample:

    pip install azure-ai-agents azure-identity azure-ai-projects jsonref

    Set these environment variables with your own values:
    1) PROJECT_ENDPOINT - The project endpoint in the format
       "https://<your-ai-services-resource-name>.services.ai.azure.com/api/projects/<your-project-name>"
    2) MODEL - The deployment name of the AI model, as found under the "Name" column in
       the "Models + endpoints" tab in your Azure AI Foundry project.
    3) Lexis_API_CONNECTION_NAME  - The name of the connection for the LexisNexis API       
        # connection id should be in the format "/subscriptions/<sub-id>/resourceGroups/<your-rg-name>/providers/Microsoft.CognitiveServices/accounts/<your-ai-services-name>/projects/<your-project-name>/connections/<your-connection-name>"
"""

import os
import jsonref
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import (
    OpenApiConnectionAuthDetails,
    OpenApiConnectionSecurityScheme,
    OpenApiTool,
)
from azure.identity import DefaultAzureCredential
																											 

# Load environment variables
endpoint = os.environ["PROJECT_ENDPOINT"]
model = os.environ["MODEL"]
connection_name = os.environ["Lexis_API_CONNECTION_NAME"]

# Load OpenAPI specification from file
with open("lexisnexis_api.json", "r") as f:
    openapi_spec = jsonref.loads(f.read())

# Initialize client with default Azure credentials
project_client = AIProjectClient(
    endpoint=endpoint,
    credential=DefaultAzureCredential(exclude_interactive_browser_credential=False),
)
# Get the connection ID using the connection name
conn_id = project_client.connections.get(name=connection_name).id

# Set up auth using the connection ID (Connect ID)
auth = OpenApiConnectionAuthDetails(
    security_scheme=OpenApiConnectionSecurityScheme(connection_id=conn_id)																					 
)

# Define OpenAPI tool with spec and auth
openapi_tool = OpenApiTool(
    name="lexisnexisapi",
    spec=openapi_spec,
    description="Web Services APIs to enable research and litigation support for LexisNexis corporate, legal",  # Tool description
    auth=auth,
)

# Agent instructions for using LexisNexis data
INSTRUCTIONS = """
You assist users in legal and compliance tasks by querying LexisNexis Web Services API. Use it to search court documents, regulatory alerts, or litigation data.
...
(Instructions continue as in your original sample)
"""
# Begin agent operations
with project_client:
    agent = project_client.agents.create_agent(
        model=model,
        name="web-services-agent",
        instructions=INSTRUCTIONS,
        tools=openapi_tool.definitions,
    )
    print(f"Created agent, ID: {agent.id}")

													
    thread = project_client.agents.threads.create()
    print(f"Created thread, ID: {thread.id}")

									   
    message = project_client.agents.messages.create(
        thread_id=thread.id,
        role="user",
        content="What are the latest regulatory alerts in the financial sector?",
    )
    print(f"Created message, ID: {message.id}")

														 
    run = project_client.agents.runs.create_and_process(
        thread_id=thread.id,
        agent_id=agent.id,
    )
    print(f"Run finished with status: {run.status}")
    if run.status == "failed":
        print(f"Run failed: {run.last_error}")

    # Print step details
    run_steps = project_client.agents.run_steps.list(thread_id=thread.id, run_id=run.id)
    for step in run_steps:
        print(f"Step {step['id']} status: {step['status']}")
        tool_calls = step.get("step_details", {}).get("tool_calls", [])
        for call in tool_calls:
            print(f"  Tool Call ID: {call.get('id')}")
            print(f"  Type: {call.get('type')}")
            function_details = call.get("function", {})
            if function_details:
                print(f"  Function name: {function_details.get('name')}")

    # Print messages in thread
    messages = project_client.agents.messages.list(thread_id=thread.id)
    for msg in messages:
        print(f"Message ID: {msg.id}, Role: {msg.role}, Content: {msg.content}")

    # Cleanup
    project_client.agents.delete_agent(agent.id)
    print("Deleted agent")
