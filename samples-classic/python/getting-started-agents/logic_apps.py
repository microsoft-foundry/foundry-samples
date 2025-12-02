# pylint: disable=line-too-long,useless-suppression
# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

"""
DESCRIPTION:
    This sample demonstrates how to use agents with Logic Apps to execute the task of sending an email.
 
PREREQUISITES:
    1) Create a Logic App within the same resource group as your Azure AI Project in Azure Portal
    2) To configure your Logic App to send emails, you must include an HTTP request trigger that is 
    configured to accept JSON with 'to', 'subject', and 'body'. The guide to creating a Logic App Workflow
    can be found here: 
    https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/agents-logic-apps#create-logic-apps-workflows-for-function-calling
    
USAGE:
    python sample_agents_logic_apps.py
 
    Before running the sample:
 
    pip install azure-ai-agents azure-identity

    Set this environment variables with your own values:
    1) PROJECT_ENDPOINT - the Azure AI Agents endpoint.
    2) MODEL_DEPLOYMENT_NAME - The deployment name of the AI model, as found under the "Name" column in 
       the "Models + endpoints" tab in your Azure AI Foundry project.

    Replace the following values in the sample with your own values:
    1) <LOGIC_APP_NAME> - The name of the Logic App you created.
    2) <TRIGGER_NAME> - The name of the trigger in the Logic App you created (the default name for HTTP
        triggers in the Azure Portal is "When_a_HTTP_request_is_received").
    3) <RECIPIENT_EMAIL> - The email address of the recipient.
"""


# Import necessary modules
import os
from typing import Set
from azure.ai.agents.models import ToolSet, FunctionTool
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient  

# Import user-defined functions and tools
from user_functions import fetch_current_datetime  # Example user function to fetch current datetime
from user_logic_apps import AzureLogicAppTool, create_send_email_function  # Logic App utilities

# [START register_logic_app]

# Create the project client to interact with Azure AI Agents service
project_client = AIProjectClient(
    endpoint=os.environ["PROJECT_ENDPOINT"],  # Azure AI Agents endpoint from environment variables
    credential=DefaultAzureCredential(),  # Use Azure Default Credential for authentication
    api_version="latest",  # Use the latest API version
)

# Extract subscription ID and resource group name from environment variables
subscription_id = os.environ["SUBSCRIPTION_ID"]
resource_group = os.environ["resource_group_name"]

# Logic App details (replace placeholders with actual values)
logic_app_name = "<LOGIC_APP_NAME>"  # Name of the Logic App
trigger_name = "<TRIGGER_NAME>"  # Name of the HTTP trigger in the Logic App

# Create and initialize the AzureLogicAppTool utility
logic_app_tool = AzureLogicAppTool(subscription_id, resource_group)
logic_app_tool.register_logic_app(logic_app_name, trigger_name)  # Register the Logic App with the tool
print(f"Registered logic app '{logic_app_name}' with trigger '{trigger_name}'.")

# Create a specialized function to send emails via the Logic App
send_email_func = create_send_email_function(logic_app_tool, logic_app_name)

# Prepare the set of functions to be used by the agent
functions_to_use: Set = {
    fetch_current_datetime,  # Function to fetch the current datetime
    send_email_func,  # Function to send emails via the Logic App
}
# [END register_logic_app]

# Use the project client within a context manager to ensure proper resource cleanup
with project_client:
    # Create a FunctionTool instance with the defined functions
    functions = FunctionTool(functions=functions_to_use)
    toolset = ToolSet()  # Initialize a ToolSet to manage tools
    toolset.add(functions)  # Add the FunctionTool to the ToolSet

    # Create an agent with the specified model, name, instructions, and tools
    agent = project_client.agents.create_agent(
        model=os.environ["MODEL_DEPLOYMENT_NAME"],  # Model deployment name from environment variables
        name="SendEmailAgent",  # Name of the agent
        instructions="You are a specialized agent for sending emails.",  # Instructions for the agent
        toolset=toolset,  # Attach the ToolSet to the agent
    )
    print(f"Created agent, ID: {agent.id}")

    # Create a thread for communication with the agent
    thread = project_client.agents.threads.create()
    print(f"Created thread, ID: {thread.id}")

    # Create a user message in the thread
    message = project_client.agents.messages.create(
        thread_id=thread.id,  # ID of the thread
        role="user",  # Role of the message sender
        content="Hello, please send an email to <RECIPIENT_EMAIL> with the date and time in '%Y-%m-%d %H:%M:%S' format.",  # Message content
    )
    print(f"Created message, ID: {message['id']}")

    # Create and process a run for the agent to handle the message
    run = project_client.agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
    print(f"Run finished with status: {run.status}")

    # Check if the run failed and log the error if applicable
    if run.status == "failed":
        print(f"Run failed: {run.last_error}")

    # Delete the agent after the interaction is complete
    project_client.agents.delete_agent(agent.id)
    print("Deleted agent")

    # Fetch and log all messages from the thread
    messages = project_client.agents.messages.list(thread_id=thread.id)
    for message in messages:
        print(f"Role: {message['role']}, Content: {message['content']}")