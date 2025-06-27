# pylint: disable=line-too-long,useless-suppression
# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

"""
DESCRIPTION:
    This sample demonstrates how to use browser automation agent operations from
    the Azure Agents service using a synchronous client.
 
USAGE:
    python browser_automation.py
 
    Before running the sample:
 
    pip install azure-ai-agents azure-identity
 
    Set these environment variables with your own values:
    1) PROJECT_ENDPOINT - The project endpoint, as found in the overview page of your
       Azure AI Foundry project.
    2) MODEL_DEPLOYMENT_NAME - The deployment name of the AI model, as found under the "Name" column in 
       the "Models + endpoints" tab in your Azure AI Foundry project.
    3) PLAYWRIGHT_CONNECTION_ID - The connection ID of the Serverless connection containing the details
         of the Playwright browser.
         Format: <AI Project resource ID>/connections/<Serverless connection name>
         Example: /subscriptions/<subscription-id>/resourceGroups/<resource_group_name>/providers/Microsoft.CognitiveServices/accounts/<account_name>/projects/<project_name>/connections/<connection-name>
"""

# <imports>
from os import environ, getenv
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import ListSortOrder
from azure.identity import DefaultAzureCredential
from typing import Any, Dict
# </imports>

# <client_initialization>
endpoint = environ["PROJECT_ENDPOINT"]
model_deployment_name = environ["MODEL_DEPLOYMENT_NAME"]
playwright_connection_id = getenv("PLAYWRIGHT_CONNECTION_ID")


with AgentsClient(
    endpoint=endpoint,
    credential=DefaultAzureCredential(exclude_interactive_browser_credential=False),
) as agents_client:
# </client_initialization>
    
    # [START create_agent_with_browser_automation_tool]
    # <browser_automation_tool_setup>
    browser_automation_tool_definition: Dict[str, Any] = {
        "type": "browser_automation",
        "browser_automation": {
            "connection": {
                "id": playwright_connection_id,
            }
        }
    }
    
    payload: Dict[str, Any] = {
        "name": "Browser Automation Tool Demo Agent",
        "description": "A demo agent that uses the browser automation tool.",
        "model": model_deployment_name,
        "instructions": "You are an agent to help me with browser automation tasks. You can answer questions, provide information, and assist with various tasks related to web browsing using the browser_automation tool available to you.",
        "tools": [browser_automation_tool_definition],
    }
    # </browser_automation_tool_setup>
    # <agent_creation>
    agent = agents_client.create_agent(
        body=payload,
    )
    print(f"Created agent, agent ID: {agent.id}")
    # [END create_agent_with_browser_automation_tool]
    # </agent_creation>

    # <thread_management>
    # Create a thread
    thread = agents_client.threads.create()
    print(f"Created thread, thread ID: {thread.id}")

    # Create a message
    message = agents_client.messages.create(
        thread_id=thread.id,
        role="user",
        content="get me the latest news from cricbuzz.com",
    )
    print(f"Created message, message ID: {message.id}")
    # </thread_management>

    # <message_processing>
    run = agents_client.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
    print(f"Run finished with status: {run.status}")

    if run.status == "failed":
        print(f"Run failed: {run.last_error}")

    # Get messages from the thread
    # Fetch and log all messages
    messages = agents_client.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
    for msg in messages:
        if msg.text_messages:
            last_text = msg.text_messages[-1]
            print(f"{msg.role}: {last_text.text.value}")

    # </message_processing>

    # <cleanup>
    # Delete the agent once done
    agents_client.delete_agent(agent.id)
    print(f"Deleted agent {agent.id}")
    # </cleanup>
