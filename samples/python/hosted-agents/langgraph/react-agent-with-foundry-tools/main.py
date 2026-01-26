# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------
import os

from azure.ai.agentserver.langgraph import from_langgraph
from azure.ai.agentserver.langgraph.tools import use_foundry_tools
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langgraph.checkpoint.memory import MemorySaver

deployment_name = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")
model = init_chat_model(
    f"azure_openai:{deployment_name}",
    azure_ad_token_provider=get_bearer_token_provider(
        DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
    )
)

foundry_tools = [
    {
        # test prompt:
        # use the python tool to calculate what is 4 * 3.82. and then find its square root and then find the square root of that result
        "type": "code_interpreter"
    }
]
if project_tool_connection_id := os.environ.get("AZURE_AI_PROJECT_TOOL_CONNECTION_ID"):
    foundry_tools.append({"type": "mcp", "project_connection_id": project_tool_connection_id})

agent = create_agent(model, checkpointer=MemorySaver(), middleware=[use_foundry_tools(foundry_tools)])

if __name__ == "__main__":
    # host the langgraph agent
    from_langgraph(agent).run()
