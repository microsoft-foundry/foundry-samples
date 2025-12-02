# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

"""
FILE: basic_agent.py

DESCRIPTION:
    This sample demonstrates how to create an agent using the Azure AI Agents service
    with an authenticated AIProjectClient.

USAGE:
    python basic_agent.py

    Before running the sample:

    pip install azure-ai-projects azure-ai-agents azure-identity

    Set these environment variables with your own values:
    PROJECT_ENDPOINT - The Azure AI Project endpoint, as found in the overview page of your
                       Azure AI Foundry project.
    MODEL_DEPLOYMENT_NAME - The AI model deployment name, to be used by your Agent, as found
                            in your AI Foundry project.
"""

# Import necessary libraries and modules
import os
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

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
    # Create an agent with the specified model, name, and instructions
    agent = project_client.agents.create_agent(
        model=model_deployment_name,  # Model deployment name
        name="my-agent",  # Name of the agent
        instructions="You are a helpful agent",  # Instructions for the agent
    )
    print(f"Created agent, agent ID: {agent.id}")

    # Create a thread for communication with the agent
    thread = project_client.agents.threads.create()
    print(f"Created thread, ID: {thread.id}")

    # Send a message to the thread
    message = project_client.agents.messages.create(
        thread_id=thread.id,  # ID of the thread
        role="user",  # Role of the message sender (e.g., user)
        content="Hello, how can I assist you today?",  # Message content
    )
    print(f"Created message, ID: {message['id']}")

    # Delete the agent when done to clean up resources
    project_client.agents.delete_agent(agent.id)
    print("Deleted agent")
