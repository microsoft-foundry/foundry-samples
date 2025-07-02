# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
"""
FILE: sample_agents_bing_grounding.py

DESCRIPTION:
    This sample demonstrates how to use agent operations with the Grounding with Bing Search tool from
    the Azure Agents service using a synchronous client.

USAGE:
    python sample_agents_bing_grounding.py

    Before running the sample:

    pip install azure.ai.projects azure-identity

    Set these environment variables with your own values:
    PROJECT_ENDPOINT - the Azure AI Project endpoint, as found in your AI Studio Project.
    AZURE_AI_CONNECTION_ID - the connection ID for the Bing Grounding tool.
    MODEL_DEPLOYMENT_NAME - the deployment name of the AI model.
"""

# Import necessary libraries and modules
import os
from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import MessageRole, BingGroundingTool
from azure.ai.projects import AIProjectClient

# Retrieve endpoint, connection ID, and model deployment name from environment variables
project_endpoint = os.environ["PROJECT_ENDPOINT"]  # Ensure the PROJECT_ENDPOINT environment variable is set
# Ensure the BING_CONNECTION_ID environment variable is set, following the format:
#"/subscriptions/<sub-id>/resourceGroups/<your-rg-name>/providers/Microsoft.CognitiveServices/accounts/<your-ai-services-name>/projects/<your-project-name>/connections/<your-bing-connection-name>"
conn_id = os.environ["BING_CONNECTION_ID"]  
model_deployment_name = os.environ["MODEL_DEPLOYMENT_NAME"]  # Ensure the MODEL_DEPLOYMENT_NAME environment variable is set

# Initialize the AIProjectClient with the endpoint and credentials
project_client = AIProjectClient(
    endpoint=project_endpoint,
    credential=DefaultAzureCredential(),  # Use Azure Default Credential for authentication
    api_version="latest",
)

with project_client:
    # Initialize the Bing Grounding tool with the connection ID
    # freshness, count, set_lang and market are optional parameters
    bing = BingGroundingTool(connection_id=conn_id, freshness="day", count=5, set_lang="en", market="us")

    # Create an agent with the specified model, name, instructions, and tools
    agent = project_client.agents.create_agent(
        model=model_deployment_name,  # Model deployment name
        name="my-agent",  # Name of the agent
        instructions="You are a helpful agent",  # Instructions for the agent
        tools=bing.definitions,  # Tools available to the agent
    )
    print(f"Created agent, ID: {agent.id}")

    # Create a thread for communication with the agent
    thread = project_client.agents.threads.create()
    print(f"Created thread, ID: {thread.id}")

    # Send a message to the thread
    message = project_client.agents.messages.create(
        thread_id=thread.id,  # ID of the thread
        role="user",  # Role of the message sender (e.g., user)
        content="What is the weather in Seattle today?",  # Message content
    )
    print(f"Created message, ID: {message['id']}")

    # Create and process an agent run in the thread using the tools
    run = project_client.agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
    print(f"Run finished with status: {run.status}")

    if run.status == "failed":
        # Log the error if the run fails
        print(f"Run failed: {run.last_error}")

    # Fetch and log all messages from the thread
    messages = project_client.agents.messages.list(thread_id=thread.id)
    for message in messages.data:
        print(f"Role: {message.role}, Content: {message.content}")

    # Delete the agent when done to clean up resources
    project_client.agents.delete_agent(agent.id)
    print("Deleted agent")
# </create run>
