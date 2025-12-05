# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
"""
FILE: azure_ai_search.py

DESCRIPTION:
    This sample demonstrates how to use agent operations with the Azure AI Search tool from
    the Azure Agents service using a synchronous client.

USAGE:
    python azure_ai_search.py

    Before running the sample:

    pip install azure.ai.projects azure-identity

    Set these environment variables with your own values:
    PROJECT_ENDPOINT - the Azure AI Project endpoint, as found in your AI Studio Project.
    MODEL_DEPLOYMENT_NAME - the deployment name of the AI model.
    AZURE_AI_CONNECTION_ID - the connection ID for the Azure AI Search tool.
"""

# Import necessary libraries and modules
import os
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import AzureAISearchQueryType, AzureAISearchTool, ListSortOrder, MessageRole

# Retrieve endpoint and model deployment name from environment variables
project_endpoint = os.environ["PROJECT_ENDPOINT"]  # Ensure the PROJECT_ENDPOINT environment variable is set
model_deployment_name = os.environ["MODEL_DEPLOYMENT_NAME"]  # Ensure the MODEL_DEPLOYMENT_NAME environment variable is set

# Initialize the AIProjectClient with the endpoint and credentials
project_client = AIProjectClient(
    endpoint=project_endpoint,
    credential=DefaultAzureCredential(exclude_interactive_browser_credential=False),  # Use Azure Default Credential for authentication
    api_version="latest",
)

with project_client:
    # Initialize the Azure AI Search tool with the required parameters
    ai_search = AzureAISearchTool(
        index_connection_id=os.environ["AZURE_AI_CONNECTION_ID"],  # Connection ID for the Azure AI Search index
        index_name="sample_index",  # Name of the search index
        query_type=AzureAISearchQueryType.SIMPLE,  # Query type (e.g., SIMPLE, FULL)
        top_k=3,  # Number of top results to retrieve
        filter="",  # Optional filter for search results
    )

    # Create an agent with the specified model, name, instructions, and tools
    agent = project_client.agents.create_agent(
        model=model_deployment_name,  # Model deployment name
        name="my-agent",  # Name of the agent
        instructions="You are a helpful agent",  # Instructions for the agent
        tools=ai_search.definitions,  # Tools available to the agent
        tool_resources=ai_search.resources,  # Resources for the tools
    )
    print(f"Created agent, ID: {agent.id}")

    # Create a thread for communication with the agent
    thread = project_client.agents.threads.create()
    print(f"Created thread, ID: {thread.id}")

    # Send a message to the thread
    message = project_client.agents.messages.create(
        thread_id=thread.id,  # ID of the thread
        role=MessageRole.USER,  # Role of the message sender (e.g., user)
        content="What is the temperature rating of the cozynights sleeping bag?",  # Message content
    )
    print(f"Created message, ID: {message['id']}")

    # Create and process an agent run in the thread using the tools
    run = project_client.agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
    print(f"Run finished with status: {run.status}")

    if run.status == "failed":
        # Log the error if the run fails
        print(f"Run failed: {run.last_error}")

    # Fetch and log all messages from the thread
    messages = project_client.agents.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
    for message in messages.data:
        print(f"Role: {message.role}, Content: {message.content}")

    # Delete the agent when done to clean up resources
    project_client.agents.delete_agent(agent.id)
    print("Deleted agent")
