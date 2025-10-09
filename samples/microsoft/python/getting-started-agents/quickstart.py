# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------
"""
FILE: quickstart.py

DESCRIPTION:
    This sample demonstrates how to use the Azure AI Agents service to perform various operations,
    including chat completions, creating and running agents, file search, and evaluating agent runs.

USAGE:
    python quickstart.py

    Before running the sample:

    pip install openai azure-ai-projects azure-identity

    Set these environment variables with your own values:
    PROJECT_ENDPOINT - The Azure AI Project endpoint, as found in your AI Studio Project.
    MODEL_DEPLOYMENT_NAME - The deployment name of the AI model.
"""

from dotenv import load_dotenv
load_dotenv()  # Load environment variables from a .env file

## - pre-reqs: install openai and azure-ai-projects packages
##   pip install openai azure-ai-projects azure-identity
## - deploy a gpt-4o model

## <chat_completion>
from azure.ai.projects.onedp import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.projects import FileSearchTool

# Initialize the AIProjectClient with endpoint and credentials
project_client = AIProjectClient(
    endpoint=os.environ["PROJECT_ENDPOINT"],  # Ensure the PROJECT_ENDPOINT environment variable is set
    credential=DefaultAzureCredential(),  # Use Azure Default Credential for authentication
    api_version="latest",
)

# Access the Azure OpenAI client for chat completions
openai = project_client.get_openai_client(api_version="2024-06-01")
response = openai.chat.completions.create(
    model=os.environ["MODEL_DEPLOYMENT_NAME"],  # Ensure the MODEL_DEPLOYMENT_NAME environment variable is set
    messages=[
        {"role": "system", "content": "You are a helpful writing assistant"},  # System message to set the assistant's behavior
        {"role": "user", "content": "Write me a poem about flowers"},  # User's request to the assistant
    ],
)

# Print the assistant's response
print(response.choices[0].message.content)
# </chat_completion>

# <create_and_run_agent>
# Create an agent with the specified model, name, and instructions
agent = project_client.agents.create_agent(
    model=os.environ["MODEL_DEPLOYMENT_NAME"],  # Model deployment name
    name="my-agent",  # Name of the agent
    instructions="You are a helpful writing assistant",  # Instructions for the agent
)
print(f"Created agent, ID: {agent.id}")

# Create a thread for communication with the agent
thread = project_client.agents.threads.create()
print(f"Created thread, ID: {thread.id}")

# Send a message to the thread
message = project_client.agents.messages.create(
    thread_id=thread.id,
    role="user",
    content="Write me a poem about flowers",  # Message content
)
print(f"Created message, ID: {message['id']}")

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
# </create_and_run_agent>


# <create_filesearch_agent>
# Upload file and create vector store
file = project.agents.files.upload(file_path="product_info_1.md", purpose="agents")
vector_store = project.agents.vector_stores.create_and_poll(file_ids=[file.id], name="my_vectorstore")

# Create file search tool and agent
file_search = FileSearchTool(vector_store_ids=[vector_store.id])
agent = project.agents.create_agent(
    model="gpt-4o",
    name="my-assistant",
    instructions="You are a helpful assistant and can search information from uploaded files",
    tools=file_search.definitions,
    tool_resources=file_search.resources,
)

# Create thread and process user message
thread = project.agents.threads.create()
project.agents.messages.create(thread_id=thread.id, role="user", content="Hello, what Contoso products do you know?")
run = project.agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)

# Handle run status
if run.status == "failed":
    print(f"Run failed: {run.last_error}")

# Cleanup resources
project.agents.vector_stores.delete(vector_store.id)
project.agents.files.delete(file_id=file.id)
project.agents.delete_agent(agent.id)

# Print thread messages
for message in project.agents.messages.list(thread_id=thread.id).text_messages:
    print(message)
# </create_filesearch_agent>

# <evaluate_agent_run>
from azure.ai.projects import EvaluatorIds

result = project.evaluation.create_agent_evaluation(
    thread=thread.id,
    run=run.id, 
    evaluators=[EvaluatorIds.AGENT_QUALITY_EVALUATOR])

# wait for evaluation to complete
result.wait_for_completion()

# result
print(result.output())
# </evaluate_agent_run>
