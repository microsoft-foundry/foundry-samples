import os
import json
from dotenv import load_dotenv
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, Tool, FunctionTool
from azure.identity import DefaultAzureCredential
from openai.types.responses.response_input_param import FunctionCallOutput, ResponseInputParam

load_dotenv()

# Define a function tool for the model to use
# <define_function_tool>
func_tool = FunctionTool(
    name="get_horoscope",
    parameters={
        "type": "object",
        "properties": {
            "sign": {
                "type": "string",
                "description": "An astrological sign like Taurus or Aquarius",
            },
        },
        "required": ["sign"],
        "additionalProperties": False,
    },
    description="Get today's horoscope for an astrological sign.",
    strict=True,
)

# Create tools list with proper typing for the agent definition
tools: list[Tool] = [mcp_tool]
# </define_function_tool>

with project_client:
    # Create a prompt agent with MCP tool capabilities
    # The agent will be able to access external GitHub repositories through the MCP protocol
    # <create_agent_with_mcp_tool>
    agent = project_client.agents.create_version(
        agent_name="MyAgent",
        definition=PromptAgentDefinition(
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            instructions="You are a helpful agent that can use MCP tools to assist users. Use the available MCP tools to answer questions and perform tasks.",
            tools=tools,
        ),
    )
    # </create_agent_with_mcp_tool>
    print(f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})")
    openai_client = project_client.get_openai_client()

    # Prompt the model with tools defined
    response = openai_client.responses.create(
        input="What is my horoscope? I am an Aquarius.",
        extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    )
    print(f"Response output: {response.output_text}")

    input_list: ResponseInputParam = []
    # Process function calls
    # <process_function_calls>
    for item in response.output:
        if item.type == "function_call":
            if item.name == "get_horoscope":
                # Execute the function logic for get_horoscope
                horoscope = get_horoscope(**json.loads(item.arguments))

                # Provide function call results to the model
                input_list.append(
                    FunctionCallOutput(
                        type="function_call_output",
                        call_id=item.call_id,
                        output=json.dumps({"horoscope": horoscope}),
                    )
                )
    # </process_function_calls>
    print("Final input:")
    print(input_list)
    response = openai_client.responses.create(
        input=input_list,
        previous_response_id=response.id,
        extra_body={"agent": {"name": agent.name, "type": "agent_reference"}},
    )

    # The model should be able to give a response!
    print("Final output:")
    print("\n" + response.output_text)

    # Uncomment these lines to clean up resources by deleting the agent version
    # This prevents accumulation of unused agent versions in your project
    # project_client.agents.delete_version(agent_name=agent.name, agent_version=agent.version)
    # print("Agent deleted")