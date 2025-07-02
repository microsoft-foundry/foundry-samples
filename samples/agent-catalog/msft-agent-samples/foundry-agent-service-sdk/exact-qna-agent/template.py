import json
import os
import re
import yaml
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import ListSortOrder, OpenApiTool, OpenApiConnectionAuthDetails, OpenApiConnectionSecurityScheme
from azure.identity import DefaultAzureCredential
from utils import bind_parameters

config = yaml.safe_load(open("./config.yaml", "r"))

project_endpoint = config["project_endpoint"]
connection_id = config["connection_id"]
model_name = config["model_name"]

# Create agent client
agents_client = AgentsClient(
    endpoint=project_endpoint,
    credential=DefaultAzureCredential(),
    api_version="2025-05-15-preview"
)

# Read in the OpenAPI spec from a file
with open("./questionanswering.json", "r") as f:
    openapi_spec = json.loads(bind_parameters(f.read(), config))

# Set up the auth details for the OpenAPI connection
auth = OpenApiConnectionAuthDetails(security_scheme=OpenApiConnectionSecurityScheme(connection_id=connection_id))

# Initialize an Agent OpenApi tool using the read in OpenAPI spec
cqa_api_tool = OpenApiTool(
    name="cqa_api",
    spec=openapi_spec,
    description= "An API to get answer to questions related to business operation",
    auth=auth
)

# Create an Agent with OpenApi tool and process Agent run
with agents_client:

    # Create the agent
    agent = agents_client.create_agent(
        model=model_name,
        name="My_CQA_Agent",
        instructions="You are question answering agent. You are requested to send the question to the cqa_tool and return the exact answer without rewriting the answer.",
        tools=cqa_api_tool.definitions
    )

    print(f"Created agent, ID: {agent.id}")

    # Create thread for communication
    thread = agents_client.threads.create()
    print(f"Created thread, ID: {thread.id}")

    # Create message to thread
    message = agents_client.messages.create(
        thread_id=thread.id,
        role="user",
        content="what is your return policy",
    )
    print(f"Created message: {message['id']}")

    # Create and process an Agent run in thread with tools
    run = agents_client.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
    print(f"Run finished with status: {run.status}")

    if run.status == "failed":
        print(f"Run failed: {run.last_error}")

    # Fetch and log all messages
    messages = agents_client.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
    for msg in messages:
        if msg.text_messages:
            last_text = msg.text_messages[-1]
            print(f"{msg.role}: {last_text.text.value}")

    # Delete the Agent when done
    agents_client.delete_agent(agent.id)
    print("Deleted agent")

