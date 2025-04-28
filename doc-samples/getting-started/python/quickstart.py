from dotenv import load_dotenv
load_dotenv()

## - pre-reqs: install openai and azure-ai-projects packages
##   pip install openai azure-ai-projects azure-identity
## - deploy a gpt-4o model

# <chat_completion>
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.projects import FileSearchTool

project = AIProjectClient(
    endpoint="https://your-foundry-resource-name.ai.azure.com/api/projects",
    credential=DefaultAzureCredential(),
)

openai = project.inference.get_azure_openai_client(api_version="2024-06-01")
response = openai.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "You are a helpful writing assistant"},
        {"role": "user", "content": "Write me a poem about flowers"},
    ],
)

print(response.choices[0].message.content)
# </chat_completion>

# <create_and_run_agent>
agent = project.agents.create_agent(
    model="gpt-4o",
    name="my-agent",
    instructions="You are a helpful writing assistant")

thread = project.agents.create_thread()
message = agents_client.create_message(
    thread_id=thread.id, 
    role="user", 
    content="Write me a poem about flowers")

run = project.agents.create_and_process_run(thread_id=thread.id, agent_id=agent.id)
if run.status == "failed":
    # Check if you got "Rate limit is exceeded.", then you want to get more quota
    print(f"Run failed: {run.last_error}")

# Get messages from the thread
messages = project.agents.list_messages(thread_id=thread.id)

# Get the last message from the sender
last_msg = messages.get_last_text_message_by_role("assistant")
if last_msg:
    print(f"Last Message: {last_msg.text.value}")

# Delete the agent once done
project.agents.delete_agent(agent.id)
print("Deleted agent")
# </create_and_run_agent>


# <create_filesearch_agent>
# Upload file and create vector store
file = project.agents.upload_file(file_path="product_info_1.md", purpose="agents")
vector_store = project.agents.create_vector_store_and_poll(file_ids=[file.id], name="my_vectorstore")

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
thread = project.agents.create_thread()
project.agents.create_message(thread_id=thread.id, role="user", content="Hello, what Contoso products do you know?")
run = project.agents.create_and_process_run(thread_id=thread.id, agent_id=agent.id)

# Handle run status
if run.status == "failed":
    print(f"Run failed: {run.last_error}")

# Cleanup resources
project.agents.delete_vector_store(vector_store.id)
project.agents.delete_file(file_id=file.id)
project.agents.delete_agent(agent.id)

# Print thread messages
for message in project.agents.list_messages(thread_id=thread.id).text_messages:
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
