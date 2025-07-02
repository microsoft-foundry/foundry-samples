## - pre-reqs: install openai and azure-ai-projects packages
##   pip install openai azure-ai-projects azure-identity
## - deploy a gpt-4o model

# <chat_completion>
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

project = AIProjectClient(
    endpoint="https://your-foundry-resource-name.ai.azure.com/api/projects/project-name",
    credential=DefaultAzureCredential(),
)

models = project.inference.get_azure_openai_client(api_version="2024-10-21")
response = models.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "You are a helpful writing assistant"},
        {"role": "user", "content": "Write me a poem about flowers"},
    ],
)

print(response.choices[0].message.content)
# </chat_completion>

# <create_and_run_agent>
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import ListSortOrder, FilePurpose

project = AIProjectClient(
    endpoint="https://your-foundry-resource-name.ai.azure.com/api/projects/project-name",
    credential=DefaultAzureCredential(),
)

agent = project.agents.create_agent(
    model="gpt-4o",
    name="my-agent",
    instructions="You are a helpful writing assistant")

thread = project.agents.threads.create()
message = project.agents.messages.create(
    thread_id=thread.id, 
    role="user", 
    content="Write me a poem about flowers")

run = project.agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
if run.status == "failed":
    # Check if you got "Rate limit is exceeded.", then you want to get more quota
    print(f"Run failed: {run.last_error}")

# Get messages from the thread
messages = project.agents.messages.list(thread_id=thread.id)

# Get the last message from the sender
messages = project.agents.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
for message in messages:
    if message.run_id == run.id and message.text_messages:
        print(f"{message.role}: {message.text_messages[-1].text.value}")

# Delete the agent once done
project.agents.delete_agent(agent.id)
print("Deleted agent")
# </create_and_run_agent>


# <create_filesearch_agent>
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import ListSortOrder, FileSearchTool

project = AIProjectClient(
    endpoint="https://your-foundry-resource-name.ai.azure.com/api/projects/project-name",
    credential=DefaultAzureCredential(),
)

# Upload file and create vector store
file = project.agents.files.upload(file_path="./product_info_1.md", purpose=FilePurpose.AGENTS)
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

# Print thread messages
messages = project.agents.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)
for message in messages:
    if message.run_id == run.id and message.text_messages:
        print(f"{message.role}: {message.text_messages[-1].text.value}")

# Cleanup resources
project.agents.vector_stores.delete(vector_store.id)
project.agents.files.delete(file_id=file.id)
project.agents.delete_agent(agent.id)

# </create_filesearch_agent>
