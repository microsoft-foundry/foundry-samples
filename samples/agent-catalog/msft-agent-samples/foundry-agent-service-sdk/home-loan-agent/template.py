import os
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FileSearchTool, CodeInterpreterTool, FilePurpose, ToolSet, MessageAttachment
from azure.identity import DefaultAzureCredential
from pathlib import Path

# Create project client using connection string, copied from your Azure AI Foundry project
# At the moment, it should be in the format "<HostName>;<AzureSubscriptionId>;<ResourceGroup>;<ProjectName>"
# Customer needs to login to Azure subscription via Azure CLI and set the environment variables
credential = DefaultAzureCredential()
project_client = AIProjectClient.from_connection_string(
    credential=credential,
    conn_str=os.environ["PROJECT_CONNECTION_STRING"]
)

# Get the current directory path
current_dir = Path(__file__).parent

# Upload the loan checklist file
checklist_file = project_client.agents.upload_file_and_poll(file_path=str(current_dir / "Contoso_Loan_Documentation_Checklist.md"), purpose=FilePurpose.AGENTS)
print(f"Uploaded file, file ID: {checklist_file.id}")

# create a vector store with the file you uploaded
vector_store = project_client.agents.create_vector_store_and_poll(file_ids=[checklist_file.id], name="my_vectorstore")
print(f"Created vector store, vector store ID: {vector_store.id}")

# create a file search tool
file_search_tool = FileSearchTool(vector_store_ids=[vector_store.id])

# Upload a file for use with Code Interpreter and add it to the client 
file = project_client.agents.upload_file_and_poll(
    file_path=str(current_dir / "loan_product_eligibility_dataset.csv"), purpose=FilePurpose.AGENTS
)
print(f"Uploaded file, file ID: {file.id}")

toolset = ToolSet()

# create a code interpreter tool
code_interpreter = CodeInterpreterTool(file_ids=[file.id])
toolset.add(code_interpreter)
toolset.add(file_search_tool)

# notices that FileSearchTool as tool and tool_resources must be added or the agent will be unable to search the file
agent = project_client.agents.create_agent(
    model="gpt-4o-mini",
    name="home-loan-guide",
    instructions="""Home Loan Guide is your expert assistant with over 10 years of experienceexperienced in mortgage lending and loan processing. I am here to simplify the mortgage application process and support borrowers in making informed decisions about their home financing. 

My primary responsibilities include:   

1. Guiding users through the mortgage application process step-by-step.   
2. Providing information on different mortgage types and interest rates.   
3. Assisting with the preparation of required documentation for application.   
4. Evaluating loan options based on user preferences and financial situations.   
5. Offering insights on credit score implications and how to improve them.   
6. Answering questions regarding loan approvals and denials.   
7. Explaining mortgage terms and payment structures in simple language.   
8. Assisting clients in understanding the closing process and associated fees. 

I combine financial logic and document awareness to provide smart, supportive advice through every phase of the mortgage journey. 
 
# Form Details 
To effectively assist you, please provide answers to the following: 

What type of mortgage are you interested in? (e.g., conventional, FHA, VA) 

What is the purchase price of the property you are considering? 

What is your estimated down payment amount? 

Do you have a pre-approval letter or any existing mortgage offers? 

What is your current credit score range, if known? 

Are there specific concerns or questions you have about the mortgage process or options? 

# Manager Feedback 
To enhance my capabilities as a Mortgage Loan Assistant, I follow these feedback insights: 

Provide real-time updates on application statuses to keep users informed. 

Use clear, jargon-free language to simplify complex mortgage concepts. 

Be proactive in offering mortgage rate comparisons and product suggestions. 

Maintain a supportive and patient demeanor throughout the application process. 

Follow up after application submissions to assist with documentation or next steps. """,
    toolset=toolset
)
print(f"Created agent, agent ID: {agent.id}")

# Create a thread
thread = project_client.agents.create_thread()
print(f"Created thread, thread ID: {thread.id}")

# Upload the user provided file as a messsage attachment
message_file = project_client.agents.upload_file_and_poll(file_path=str(current_dir / "Contoso_Loan_Documentation_Checklist.md"), purpose=FilePurpose.AGENTS)
print(f"Uploaded file, file ID: {message_file.id}")

# Create a message with the file search attachment
# Notice that vector store is created temporarily when using attachments with a default expiration policy of seven days.
attachment = MessageAttachment(file_id=message_file.id, tools=FileSearchTool().definitions)
message = project_client.agents.create_message(
    thread_id=thread.id, role="user", content="What documents do I need for a Contoso Bank loan?", attachments=[attachment]
)
print(f"Created message, message ID: {message.id}")

run = project_client.agents.create_and_process_run(thread_id=thread.id, agent_id=agent.id)
print(f"Created run, run ID: {run.id}")

project_client.agents.delete_vector_store(vector_store.id)
print("Deleted vector store")

project_client.agents.delete_file(file.id)
print("Deleted file")

project_client.agents.delete_agent(agent.id)
print("Deleted agent")

messages = project_client.agents.list_messages(thread_id=thread.id)
print(f"Messages: {messages}")
