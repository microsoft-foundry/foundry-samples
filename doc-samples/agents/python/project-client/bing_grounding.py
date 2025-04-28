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

    Set this environment variables with your own values:
    PROJECT_CONNECTION_STRING - the Azure AI Project connection string, as found in your AI Studio Project.
    BING_CONNECTION_NAME - the name of the connection of Grounding with Bing Search
    
"""
# <create a project client>
from azure.identity import DefaultAzureCredential
from azure.ai.projects.onedp import AIProjectClient
from azure.ai.agents.models import BingGroundingTool


# Create an Azure AI Client from a connection string, copied from your AI Studio project.
# At the moment, it should be in the format "<HostName>;<AzureSubscriptionId>;<ResourceGroup>;<HubName>"
# Customer needs to login to Azure subscription via Azure CLI and set the environment variables
# connection string should be copied from the project in AI Studio

# Example: project_endpoint = "https://<your-ai-services-resource-name>.services.ai.azure.com/api/projects/<your-project-name>"

project_endpoint = ""

# Takes an endpoint and a credential to create a project client
project_client = AIProjectClient(
    endpoint=project_endpoint,
    credential=DefaultAzureCredential(),
)
# </create a project client>

# Decision 1: Dp we actually need to create a project client here?
# Decision 2: Is there an easier way to get the connection name using the default connections

# <create agent>
# Example connection_id= "/subscriptions/<sub-id>/resourceGroups/<your-rg-name>/providers/Microsoft.CognitiveServices/accounts/<your-ai-services-name>/projects/<your-project-name>/connections/<your-bing-connection-name>"
conn_id = ""

print(conn_id)

# Initialize agent bing tool and add the connection id
bing = BingGroundingTool(connection_id=conn_id)

# Create agent with the bing tool and process assistant run
with project_client:
    agents_client = project_client.agents.get_client()

    agent = agents_client.create_agent(
        model="gpt-4o",
        name="my-agent",
        instructions="use the tool to respond",
        tools=bing.definitions,
    )
    print(f"Created agent, ID: {agent.id}")
    # </create agent>

    # <create thread>
    # Create thread for communication
    thread = agents_client.create_thread()
    print(f"Created thread, ID: {thread.id}")

    # Create message to thread
    message = agents_client.create_message(
        thread_id=thread.id,
        role="user",
        content="How is the weather in Seattle today?",
    )
    print(f"Created message, ID: {message.id}")
    # </create thread>

    # <create run>
    # Create and process agent run in thread with tools
    run = agents_client.create_and_process_run(thread_id=thread.id, agent_id=agent.id)
    print(f"Run finished with status: {run.status}")

    if run.status == "failed":
        print(f"Run failed: {run.last_error}")

    run_steps = agents_client.list_run_steps(run_id=run.id, thread_id=thread.id)
    run_steps_data = run_steps["data"]
    # print(f"Last run step detail: {run_steps_data[-1]}")
    print(f"Last run step detail: {run_steps_data}")

    # Delete the assistant when done
    agents_client.delete_agent(agent.id)
    print("Deleted agent")

    # Fetch and log all messages
    messages = agents_client.list_messages(thread_id=thread.id)
    print(f"Messages: {messages}")
# </create run>
