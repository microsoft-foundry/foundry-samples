import os
import jsonref
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import OpenApiTool, OpenApiConnectionAuthDetails, OpenApiConnectionSecurityScheme

# endpoint should be in the format "https://<your-ai-services-resource-name>.services.ai.azure.com/api/projects/<your-project-name>"
endpoint = os.environ["PROJECT_ENDPOINT"]
model = os.environ["MODEL"]
# connection id should be in the format "/subscriptions/<sub-id>/resourceGroups/<your-rg-name>/providers/Microsoft.CognitiveServices/accounts/<your-ai-services-name>/projects/<your-project-name>/connections/<your-connection-name>"
conn_id = os.environ["CONNECTION_ID"]

with AIProjectClient(
    endpoint=endpoint,
    credential=DefaultAzureCredential(exclude_interactive_browser_credential=False),
) as project_client:
    # </initialization>

    # Load the OpenAPI specification for the service from a local JSON file using jsonref to handle references
    with open("./Trademo_OpenAPI.json", "r") as f:
        openapi_spec = jsonref.loads(f.read())

    # Create Auth object for the OpenApiTool (note that connection or managed identity auth setup requires additional setup in Azure)
    auth = OpenApiConnectionAuthDetails(security_scheme=OpenApiConnectionSecurityScheme(connection_id=conn_id))

    # Initialize the main OpenAPI tool definition for weather
    openapi_tool = OpenApiTool(
        name="Trademo_Shipments_And_Tariff", 
        spec=openapi_spec, 
        description="Provides latest duties and past shipment and duty data for trade between multiple countries", 
        auth=auth
    )

    # <agent_creation>
    # --- Agent Creation ---
    # Create an agent configured with the combined OpenAPI tool definitions
    agent = project_client.agents.create_agent(
        model=model,
        name="my-agent",
        instructions="You are a helpful shipment agent. Your job is to retrieve shipments and tariff related data till year 2025 using Trademo_Shipments_And_Tariff tool. Also only show tariff information when explicitly asked to do so by the user.", # Define agent's role
        tools=openapi_tool.definitions, 
    )
    print(f"Created agent, ID: {agent.id}")
    # </agent_creation>

    # <thread_management>
    # --- Thread Management ---
    # Create a new conversation thread for the interaction
    thread = project_client.agents.threads.create()
    print(f"Created thread, ID: {thread.id}")

    # Create the initial user message in the thread
    message = project_client.agents.messages.create(
        thread_id=thread.id,
        role="user",
        # give an example of a user message that the agent can respond to
        content="what is the duty of import for jewllery(HS code =  711319) from India to US?",
    )
    print(f"Created message, ID: {message.id}")
    # </thread_management>

    # <message_processing>
    run = project_client.agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
    print(f"Run finished with status: {run.status}")
    # </message_processing>

    # <tool_execution_loop> # Note: This section now processes completed steps, as create_and_process_run handles execution
    # --- Post-Run Step Analysis ---
    if run.status == "failed":
        print(f"Run failed: {run.last_error}")

    # Retrieve the steps taken during the run for analysis
    run_steps = project_client.agents.run_steps.list(thread_id=thread.id, run_id=run.id)

    # Loop through each step to display information
    for step in run_steps:
        print(f"Step {step['id']} status: {step['status']}")

        # Check if there are tool calls recorded in the step details
        step_details = step.get("step_details", {})
        tool_calls = step_details.get("tool_calls", [])

        if tool_calls:
            print("  Tool calls:")
            for call in tool_calls:
                print(f"    Tool Call ID: {call.get('id')}")
                print(f"    Type: {call.get('type')}")

                function_details = call.get("function", {})
                if function_details:
                    print(f"    Function name: {function_details.get('name')}")
        print() # Add an extra newline between steps for readability
    # </tool_execution_loop>

    # <cleanup>
    # --- Cleanup ---
    # Delete the agent resource to clean up
    project_client.agents.delete_agent(agent.id)
    print("Deleted agent")

    # Fetch and log all messages exchanged during the conversation thread
    messages = project_client.agents.messages.list(thread_id=thread.id)
    for message in messages:
        print(f"Message ID: {message.id}, Role: {message.role}, Content: {message.content}")
    # </cleanup>