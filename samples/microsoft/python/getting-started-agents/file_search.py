# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
"""
FILE: file_search.py

DESCRIPTION:
    This sample demonstrates how to use agent operations with the File Search tool from
    the Azure Agents service using a synchronous client.

USAGE:
    python file_search.py

    Before running the sample:

    pip install azure-ai-projects azure-identity

    Set these environment variables with your own values:
    PROJECT_ENDPOINT - The Azure AI Project endpoint, as found in your AI Studio Project.
    MODEL_DEPLOYMENT_NAME - The deployment name of the AI model.
"""

import os
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.agents.models import (
    FileSearchTool,
    FilePurpose,
)

# Define the path to the asset file to be uploaded
asset_file_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../assets/product_info_1.md"))

# Retrieve environment variables for endpoint and model deployment name
project_endpoint = os.environ["PROJECT_ENDPOINT"]  # Ensure the PROJECT_ENDPOINT environment variable is set
model_deployment_name = os.environ["MODEL_DEPLOYMENT_NAME"]  # Ensure the MODEL_DEPLOYMENT_NAME environment variable is set

# Initialize the AIProjectClient with the endpoint and credentials
project_client = AIProjectClient(
    endpoint=project_endpoint,
    credential=DefaultAzureCredential(exclude_interactive_browser_credential=False),  # Use Azure Default Credential for authentication
    api_version="latest",
)

with project_client:
    # Access the agents client from the project client
    agents_client = project_client.agents

    # Upload the file and specify its purpose
    file = agents_client.files.upload_and_poll(file_path=asset_file_path, purpose=FilePurpose.AGENTS)
    print(f"Uploaded file, file ID: {file.id}")

    # Create a vector store using the uploaded file
    vector_store = agents_client.vector_stores.create_and_poll(file_ids=[file.id], name="my_vectorstore")
    print(f"Created vector store, vector store ID: {vector_store.id}")

    # Create a file search tool using the vector store
    file_search = FileSearchTool(vector_store_ids=[vector_store.id])

    # Create an agent with the specified model, name, instructions, and tools
    agent = project_client.agents.create_agent(
        model=model_deployment_name,  # Model deployment name
        name="my-agent",  # Name of the agent
        instructions="You are a helpful agent and can search information from uploaded files",  # Instructions for the agent
        tools=file_search.definitions,  # Tools available to the agent
        tool_resources=file_search.resources,  # Resources for the tools
    )
    print(f"Created agent, ID: {agent.id}")

    # Create a thread for communication with the agent
    thread = project_client.agents.threads.create()
    print(f"Created thread, ID: {thread.id}")

    # Send a message to the thread
    message = project_client.agents.messages.create(
        thread_id=thread.id,
        role="user",
        content="Hello, what Contoso products do you know?",  # Message content
    )
    print(f"Created message, ID: {message['id']}")

    # Create and process a run with the specified thread and agent
    run = project_client.agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
    print(f"Run finished with status: {run.status}")

    if run.status == "failed":
        # Log the error if the run fails
        print(f"Run failed: {run.last_error}")

    # Cleanup resources after use
    # Delete the vector store
    project_client.agents.vector_stores.delete(vector_store.id)
    print("Deleted vector store")

    # Delete the uploaded file
    project_client.agents.files.delete(file_id=file.id)
    print("Deleted file")

    # Delete the agent
    project_client.agents.delete_agent(agent.id)
    print("Deleted agent")

    # Fetch and log all messages from the thread
    messages = project_client.agents.messages.list(thread_id=thread.id)
    for message in messages.data:
        print(f"Role: {message.role}, Content: {message.content}")