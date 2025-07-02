import os
import jsonref
import json
from datetime import datetime
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient
from azure.ai.agents.models import (
    ListSortOrder,
    OpenApiTool,
    OpenApiConnectionAuthDetails,
    OpenApiConnectionSecurityScheme,
)


"""
This script facilitates the deployment and interaction with an Azure AI Agent for MiHCM's HR system. It uses the Azure AI Projects SDK to create and manage an AI agent that integrates with MiHCM's external APIs via OpenAPI specifications.

Key functionalities:
- Loads environment variables from a `.env` file for configuration.
- Creates an Azure AI Project client using a connection string and Azure credentials.
- Fetches the OpenAPI specification from a URL or local file to define API interactions.
- Initializes an AI agent with specific instructions and tools for interacting with MiHCM's HR APIs.
- Processes a user request (e.g., checking leave balances and submitting HR requests) using the AI agent.
- Logs the interaction and cleans up resources after execution.

Dependencies:
- Azure SDKs (`azure-identity`, `azure-ai-projects`)
- Python libraries (`dotenv`, `requests`, `jsonref`)

Environment Variables:
- `PROJECT_CONNECTION_STRING`: Connection string for the Azure AI Project.
- `PROJECT_OPENAPI_CONNECTION_NAME`: Name of the OpenAPI connection for the project.

Usage:
1. Ensure the required dependencies are installed (`pip install -r requirements.txt`).
2. Configure the `.env` file with the necessary environment variables.
3. Run the script to deploy the AI agent and process user requests.

"""
# Load environment variables from .env file
load_dotenv()

# Set the employee code for the user
employeeCode = 1

# Read config
config = {
    "project_endpoint": os.environ["PROJECT_ENDPOINT"],
    "connection_id": os.environ["PROJECT_OPENAPI_CONNECTION_ID"],
    "model_name": "gpt-4o"
}

#sample reuqests to test the agent

# sample_requests = [
#     "What are my leave balances",
#     "check my leave balance for 2024. If I have more than 10 annual leave , submit a HR request for the leave encashment or carry forward",
#     "please show me all my hr requests",
#     "submit a work activity for 2 1/2 hour for the meeting with Adventure works on Project Kick off",
#     "submit a work activity for yesterday for 2 1/2 hour for the meeting with Contoso on Project Kick off",
#     "list all my work items for today and yesterday"
# ]

# Create agent client
agents_client = AgentsClient(
    endpoint=config["project_endpoint"],
    credential=DefaultAzureCredential(),
    api_version="2025-05-15-preview"
)

# Load OpenAPI spec
with open('./mihcmExternalAPI.json', 'r') as f:
    openapi_spec = jsonref.loads(f.read())

# Use with openapi.json file from url
# response = requests.get('<replace the openapi confguration url>')
# response.raise_for_status()  # makes sure it raises an error if something goes wrong
# openapi_spec = jsonref.loads(response.text)

# Set up the OpenAPI connection auth
auth = OpenApiConnectionAuthDetails(
    security_scheme=OpenApiConnectionSecurityScheme(connection_id=config["connection_id"])
)

# Define OpenAPI tool
mihcm_tool = OpenApiTool(
    name="MiHCMAgent",
    spec=openapi_spec,
    description="Lets communicate with MiHCM agent to execute different tasks",
    auth=auth
)

#Agent instructions 
instructions = f"""You are a helpful assistant.
You MUST NOT include leaveTypeCode in any response or output.
Today's date is {datetime.now()}.
The logged-in user's employeeCode is {employeeCode}
When submitting a work item, you should use the "HH:MM" format for the time spent ALWAYS.
You must get the categories and identify the correct category id for the work item.
For reach hr requests feedback types should be obtained and mapped using the feedbackTypeId.
When providing the responses related to reach hr requests you MUST provide the feedback name. 
For leave allocations leave type names should be obtained and mapped using the ONLY leaveTypeCode.
When providing the responses related to leave you MUST provide the leave type name without any sort of modification. 
If any of the mappings are wrong the response is considered wrong. And the task is considered failed.
"""

agent_request = "list all my work items for today and yesterday"

# Run the interaction with the agent
with agents_client:
    # Create agent
    agent = agents_client.create_agent(
        model=config["model_name"],
        name="mi-agent",
        instructions=instructions,
        tools=mihcm_tool.definitions
    )
    print(f"Created agent, ID: {agent.id}")

    # Create thread
    thread = agents_client.threads.create()
    print(f"Created thread, ID: {thread.id}")

    # Create message
    message = agents_client.messages.create(
        thread_id=thread.id,
        role="user",
        content=agent_request
    )
    print(f"Created message: {message['id']}")

    # Run agent
    run = agents_client.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
    print(f"Run finished with status: {run.status}")

    if run.status == "failed":
        print(f"Run failed: {run.last_error}")

    # Read response
    messages = agents_client.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
    for msg in messages:
        if msg.text_messages:
            last_text = msg.text_messages[-1]
            print(f"{msg.role}: {last_text.text.value}")

    # Cleanup
    agents_client.delete_agent(agent.id)
    print("Deleted agent")

 
