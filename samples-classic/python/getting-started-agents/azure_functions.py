# pylint: disable=line-too-long,useless-suppression
# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

"""
DESCRIPTION:
    This sample demonstrates how to use azure function agent operations from
    the Azure Agents service using a synchronous client.
 
USAGE:
    python sample_agents_azure_functions.py
 
    Before running the sample:
 
    pip install azure-ai-agents azure-identity
 
    Set these environment variables with your own values:
    1) PROJECT_ENDPOINT - the Azure AI Agents endpoint.
    2) MODEL_DEPLOYMENT_NAME - The deployment name of the AI model, as found under the "Name" column in 
       the "Models + endpoints" tab in your Azure AI Foundry project.
    3) STORAGE_SERVICE_ENDPONT - the storage service queue endpoint, triggering Azure function.
       Please see Getting Started with Azure Functions page for more information on Azure Functions:
       https://learn.microsoft.com/azure/azure-functions/functions-get-started
"""

# Import necessary modules
import os
from azure.ai.agents.models import AzureFunctionStorageQueue, AzureFunctionTool, MessageRole
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient  # Import AIProjectClient for consistency

# Initialize the project endpoint from environment variables
project_endpoint = os.environ["PROJECT_ENDPOINT"]

# Create an AIProjectClient instance to interact with the Azure AI Agents service
project_client = AIProjectClient(
    endpoint=project_endpoint,
    credential=DefaultAzureCredential(),
    api_version="latest",  # Use the latest API version
)

# Use the project client within a context manager to ensure proper resource cleanup
with project_client:
    # Retrieve the storage service endpoint from environment variables
    storage_service_endpoint = os.environ["STORAGE_SERVICE_ENDPONT"]

    # [START create_agent_with_azure_function_tool]
    # Define an Azure Function Tool with input and output queue configurations
    azure_function_tool = AzureFunctionTool(
        name="foo",  # Name of the tool
        description="Get answers from the foo bot.",  # Description of the tool's purpose
        parameters={  # Define the parameters required by the tool
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The question to ask."},
                "outputqueueuri": {"type": "string", "description": "The full output queue uri."},
            },
        },
        input_queue=AzureFunctionStorageQueue(  # Input queue configuration
            queue_name="azure-function-foo-input",
            storage_service_endpoint=storage_service_endpoint,
        ),
        output_queue=AzureFunctionStorageQueue(  # Output queue configuration
            queue_name="azure-function-tool-output",
            storage_service_endpoint=storage_service_endpoint,
        ),
    )

    # Create an agent with the Azure Function Tool
    agent = project_client.agents.create_agent(
        model=os.environ["MODEL_DEPLOYMENT_NAME"],  # Model deployment name from environment variables
        name="azure-function-agent-foo",  # Name of the agent
        instructions=(
            "You are a helpful support agent. Use the provided function any time the prompt contains the string "
            "'What would foo say?'. When you invoke the function, ALWAYS specify the output queue uri parameter as "
            f"'{storage_service_endpoint}/azure-function-tool-output'. Always responds with \"Foo says\" and then the response from the tool."
        ),
        tools=azure_function_tool.definitions,  # Attach the tool definitions to the agent
    )
    print(f"Created agent, agent ID: {agent.id}")
    # [END create_agent_with_azure_function_tool]

    # Create a new thread for the agent to interact with
    thread = project_client.agents.threads.create()
    print(f"Created thread, thread ID: {thread.id}")

    # Create a user message in the thread
    message = project_client.agents.messages.create(
        thread_id=thread.id,  # ID of the thread
        role="user",  # Role of the message sender
        content="What is the most prevalent element in the universe? What would foo say?",  # Message content
    )
    print(f"Created message, message ID: {message['id']}")

    # Create and process a run for the agent to handle the message
    run = project_client.agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
    print(f"Run finished with status: {run.status}")

    # Check if the run failed and log the error if applicable
    if run.status == "failed":
        print(f"Run failed: {run.last_error}")

    # Retrieve and print all messages from the thread
    messages = project_client.agents.messages.list(thread_id=thread.id)
    for msg in messages:
        print(f"Role: {msg['role']}, Content: {msg['content']}")

    # Delete the agent after the interaction is complete
    project_client.agents.delete_agent(agent.id)
    print(f"Deleted agent {agent.id}")