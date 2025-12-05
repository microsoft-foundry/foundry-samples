# ------------------------------------
# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.
# ------------------------------------

"""
DESCRIPTION:
    This sample demonstrates how to use agent operations with custom functions from
    the Azure Agents service using a synchronous client.

USAGE:
    python sample_agents_functions.py

    Before running the sample:

    pip install azure-ai-agents azure-identity

    Set these environment variables with your own values:
    1) PROJECT_ENDPOINT - the Azure AI Agents endpoint.
    2) MODEL_DEPLOYMENT_NAME - The deployment name of the AI model, as found under the "Name" column in 
       the "Models + endpoints" tab in your Azure AI Foundry project.
"""
# Import necessary modules
import os, time
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient  # Import AIProjectClient for consistency
from azure.ai.agents.models import FunctionTool, RequiredFunctionToolCall, SubmitToolOutputsAction, ToolOutput

# Retrieve the project endpoint from environment variables
project_endpoint = os.environ["PROJECT_ENDPOINT"]

# Initialize the AIProjectClient with the endpoint and credentials
project_client = AIProjectClient(
    endpoint=project_endpoint,  # Azure AI Agents endpoint
    credential=DefaultAzureCredential(),  # Use Azure Default Credential for authentication
    api_version="latest",  # Use the latest API version
)

# Initialize the FunctionTool with user-defined functions
functions = FunctionTool(functions=user_functions)

# Use the project client within a context manager to ensure proper resource cleanup
with project_client:
    # Create an agent with custom functions
    agent = project_client.agents.create_agent(
        model=os.environ["MODEL_DEPLOYMENT_NAME"],  # Model deployment name from environment variables
        name="my-agent",  # Name of the agent
        instructions="You are a helpful agent",  # Instructions for the agent
        tools=functions.definitions,  # Attach the function tool definitions to the agent
    )
    print(f"Created agent, ID: {agent.id}")

    # Create a new thread for communication with the agent
    thread = project_client.agents.threads.create()
    print(f"Created thread, ID: {thread.id}")

    # Create a user message in the thread
    message = project_client.agents.messages.create(
        thread_id=thread.id,  # ID of the thread
        role="user",  # Role of the message sender
        content="Hello, send an email with the datetime and weather information in New York?",  # Message content
    )
    print(f"Created message, ID: {message['id']}")

    # Create and process a run for the agent to handle the message
    run = project_client.agents.runs.create_and_process(thread_id=thread.id, agent_id=agent.id)
    print(f"Created run, ID: {run.id}")

    # Poll the run status until it is completed or requires action
    while run.status in ["queued", "in_progress", "requires_action"]:
        time.sleep(1)  # Wait for 1 second before checking the status again
        run = project_client.agents.runs.get(thread_id=thread.id, run_id=run.id)

        # Handle cases where the run requires action
        if run.status == "requires_action" and isinstance(run.required_action, SubmitToolOutputsAction):
            tool_calls = run.required_action.submit_tool_outputs.tool_calls
            if not tool_calls:
                # Cancel the run if no tool calls are provided
                print("No tool calls provided - cancelling run")
                project_client.agents.runs.cancel(thread_id=thread.id, run_id=run.id)
                break

            tool_outputs = []
            for tool_call in tool_calls:
                if isinstance(tool_call, RequiredFunctionToolCall):
                    try:
                        # Execute the tool call and collect the output
                        print(f"Executing tool call: {tool_call}")
                        output = functions.execute(tool_call)
                        tool_outputs.append(
                            ToolOutput(
                                tool_call_id=tool_call.id,  # ID of the tool call
                                output=output,  # Output of the tool call
                            )
                        )
                    except Exception as e:
                        # Log any errors encountered during tool execution
                        print(f"Error executing tool_call {tool_call.id}: {e}")

            print(f"Tool outputs: {tool_outputs}")
            if tool_outputs:
                # Submit the tool outputs back to the agent
                project_client.agents.runs.submit_tool_outputs(
                    thread_id=thread.id, run_id=run.id, tool_outputs=tool_outputs
                )

        print(f"Current run status: {run.status}")

    # Log the final status of the run
    print(f"Run completed with status: {run.status}")

    # Delete the agent after the interaction is complete
    project_client.agents.delete_agent(agent.id)
    print("Deleted agent")

    # Fetch and log all messages from the thread
    messages = project_client.agents.messages.list(thread_id=thread.id)
    for message in messages:
        print(f"Role: {message['role']}, Content: {message['content']}")