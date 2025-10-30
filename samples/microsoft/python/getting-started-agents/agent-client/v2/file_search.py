from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, FileSearchTool
import os

# Load the file to be indexed for search
file_1 = os.path.abspath(os.path.join(os.path.dirname(__file__), "../assets/product_info.md"))

project_client = AIProjectClient(
    endpoint=os.environ["AZURE_AI_PROJECT_ENDPOINT"],
    credential=DefaultAzureCredential(),
)

openai_client = project_client.get_openai_client()

# Create vector store for file search

# <create_vector_store_basic>
vector_store = openai_client.vector_stores.create(name="ProductInfoStore")
print(f"Vector store created (id: {vector_store.id})")
# </create_vector_store_basic>

# Create vector store with expiration

# <create_vector_store_with_expiration>
vector_store_with_expiration = openai_client.vector_stores.create_and_poll(
  name="Product Documentation",
  file_ids=[file_1.id],
  expires_after={
      "anchor": "last_active_at",
      "days": 7
  }
)
# </create_vector_store_with_expiration>

with project_client:
    # Create agent with file search tool
    # <create_agent_with_file_search_tool>
    agent = project_client.agents.create_version(
        agent_name="MyAgent",
        definition=PromptAgentDefinition(
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            instructions="You are a helpful assistant that can search through product information.",
            tools=[FileSearchTool(vector_store_ids=[vector_store.id])],
        ),
        description="File search agent for product information queries.",
    )
    # </create_agent_with_file_search_tool>
    print(f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})")

    # Create a conversation for the agent interaction
    conversation = openai_client.conversations.create()
    print(f"Created conversation (id: {conversation.id})")

    # Send a query to search through the uploaded file
    response = openai_client.responses.create(
        conversation=conversation.id,
        input="Tell me about Contoso products",
        extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    )
    print(f"Response: {response.output_text}")

    print("\nCleaning up...")
    # <delete_vector_store>
    openai_client.vector_stores.delete(vector_store.id)
    print("Deleted vector store")
    # </delete_vector_store>
    
    # Uncomment the following lines to delete the agent after testing
    #project_client.agents.delete_version(agent_name=agent.name, agent_version=agent.version)
    #print("Agent deleted")

    