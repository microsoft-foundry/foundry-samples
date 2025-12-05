# pylint: disable=line-too-long,useless-suppression
# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
"""
FILE: enterprise_search.py

DESCRIPTION:
    This sample demonstrates how to use agent operations with the Code Interpreter tool from
    the Azure Agents service using a synchronous client.

USAGE:
    python enterprise_search.py

    Before running the sample:

    pip install azure-ai-agents azure-identity

    Set these environment variables with your own values:
    1) PROJECT_ENDPOINT - The Azure AI Agents endpoint.
    2) MODEL_DEPLOYMENT_NAME - The deployment name of the AI model, as found under the "Name" column in 
       the "Models + endpoints" tab in your Azure AI Foundry project.
"""

# Import necessary libraries and modules
import os
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import (
    CodeInterpreterTool,  # Tool for enabling code interpretation capabilities
    MessageAttachment,  # Represents an attachment to a message
    VectorStoreDataSource,  # Data source for vector store creation
    VectorStoreDataSourceAssetType,  # Enum for specifying the type of vector store asset
)
from azure.identity import DefaultAzureCredential  # For authentication
from azure.ai.projects import AIProjectClient  # Client to interact with Azure AI Projects

# Retrieve the endpoint and model deployment name from environment variables
project_endpoint = os.environ["PROJECT_ENDPOINT"]  # Ensure the PROJECT_ENDPOINT environment variable is set
model_deployment_name = os.environ["MODEL_DEPLOYMENT_NAME"]  # Ensure the MODEL_DEPLOYMENT_NAME environment variable is set

# Initialize the AIProjectClient with the endpoint and credentials
project_client = AIProjectClient(
    endpoint=project_endpoint,
    credential=DefaultAzureCredential(exclude_interactive_browser_credential=False),  # Use Azure Default Credential for authentication
    api_version="latest",
)

with project_client:
    # Initialize the CodeInterpreterTool for enabling code interpretation
    code_interpreter = CodeInterpreterTool()

    # Create an agent with the specified model, name, instructions, and tools
    agent = project_client.agents.create_agent(
        model=model_deployment_name,  # Model deployment name
        name="my-agent",  # Name of the agent
        instructions="You are a helpful agent",  # Instructions for the agent
        tools=code_interpreter.definitions,  # Tools to be used by the agent
    )
    print(f"Created agent, agent ID: {agent.id}")

    # Create a thread for communication with the agent
    thread = project_client.agents.threads.create()
    print(f"Created thread, thread ID: {thread.id}")

    # Upload a file and create a message with the CodeInterpreterTool
    asset_uri = os.environ["AZURE_BLOB_URI"]  # Ensure the AZURE_BLOB_URI environment variable is set
    ds = VectorStoreDataSource(asset_identifier=asset_uri, asset_type=VectorStoreDataSourceAssetType.URI_ASSET)
    attachment = MessageAttachment(data_source=ds, tools=code_interpreter.definitions)
    message = project_client.agents.messages.create(
        thread_id=thread.id,
        role="user",
        content="What does the attachment say?",
        attachments=[attachment],
    )
    print(f"Created message, message ID: {message['id']}")

    # Create and process a run with the specified thread and agent
    run = project_client.agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
    print(f"Run finished with status: {run.status}")

    if run.status == "failed":
        # Log the error if the run fails
        print(f"Run failed: {run.last_error}")

    # Fetch and log all messages from the thread
    messages = project_client.agents.messages.list(thread_id=thread.id)
    for message in messages.data:
        print(f"Role: {message.role}, Content: {message.content}")

    # Delete the agent after use
    project_client.agents.delete_agent(agent.id)
    print("Deleted agent")