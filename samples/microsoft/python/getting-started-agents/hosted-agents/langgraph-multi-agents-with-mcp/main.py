import os
import logging
import asyncio

from dotenv import load_dotenv
from typing import Literal, List

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.tools import StructuredTool
from langgraph.graph import (
    END,
    START,
    MessagesState,
    StateGraph,
)
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.monitor.opentelemetry import configure_azure_monitor

from azure.ai.agentserver.langgraph import from_langgraph


logger = logging.getLogger(__name__)

load_dotenv()

if os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    configure_azure_monitor(enable_live_metrics=True, logger_name="__main__")

deployment_name = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o-mini")

try:
    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(
        credential, "https://cognitiveservices.azure.com/.default"
    )
    llm = init_chat_model(
        f"azure_openai:{deployment_name}",
        azure_ad_token_provider=token_provider,
    )
except Exception:
    logger.exception("Calculator Agent failed to start")
    raise


# Define tools
def make_system_prompt(suffix: str) -> str:
    return (
        "You are a helpful AI assistant, collaborating with other assistants."
        " Use the provided tools to progress towards answering the question."
        " If you are unable to fully answer, that's OK, another assistant with different tools "
        " will help where you left off. Execute what you can to make progress."
        " If you or any of the other assistants have the final answer or deliverable,"
        " prefix your response with FINAL ANSWER so the team knows to stop."
        f"\n{suffix}"
    )


def word_count_tool(text: str) -> int:
    """A tool that counts the number of words in a given text."""
    return len(text.split())


def get_next_node(last_message: BaseMessage, goto: str):
    if "FINAL ANSWER" in last_message.content:
        # Any agent decided the work is done
        return END
    return goto

# word count agent and node
word_count_agent = create_agent(
    llm,
    [word_count_tool],
    system_prompt=make_system_prompt(
        "You can only count words in a string. You are working with a researcher colleague."
    ),
)


def word_count_node(state: MessagesState) -> Command[Literal["researcher", END]]:
    result = word_count_agent.invoke(state)
    goto = get_next_node(result["messages"][-1], "researcher")
    # wrap in a human message, as not all providers allow
    # AI message at the last position of the input messages list
    result["messages"][-1] = HumanMessage(
        content=result["messages"][-1].content, name="word_counter"
    )
    return Command(
        update={
            # share internal message history of chart agent with other agents
            "messages": result["messages"],
        },
        goto=goto,
    )

def build_researcher_node(tools):
    async def research_node(
        state: MessagesState,
    ) -> Command[Literal["word_counter", END]]:
        # Research agent and node
        research_agent = create_agent(
            llm,
            tools=tools,
            system_prompt=make_system_prompt(
                "You can only do research. You are working with a word count agent colleague."
            ),
        )

        result = await research_agent.ainvoke(state)
        goto = get_next_node(result["messages"][-1], "word_counter")
        # wrap in a human message, as not all providers allow
        # AI message at the last position of the input messages list
        result["messages"][-1] = HumanMessage(
            content=result["messages"][-1].content, name="researcher"
        )
        return Command(
            update={
                # share internal message history of research agent with other agents
                "messages": result["messages"],
            },
            goto=goto,
        )
    
    return research_node


# Build workflow
def build_agent(tools) -> "StateGraph":
    research_node = build_researcher_node(tools)

    workflow = StateGraph(MessagesState)
    workflow.add_node("researcher", research_node)
    workflow.add_node("word_counter", word_count_node)

    workflow.add_edge(START, "researcher")

    # Compile the agent
    return workflow.compile()


def create_graph_factory():
    """Create a factory function that builds a graph with ToolClient.
    
    This function returns a factory that takes a ToolClient and returns
    a CompiledStateGraph. The graph is created at runtime for every request,
    allowing it to access the latest tool configuration dynamically.
    """

    async def graph_factory(tools: List[StructuredTool]) -> CompiledStateGraph:
        print("\nCreating LangGraph agent with tools from factory...")
        agent = build_agent(tools)
        print("Agent created successfully!")
        return agent
    
    return graph_factory


async def quickstart():
    """Build and return a LangGraphAdapter using a graph factory function."""
    
    # Get configuration from environment
    project_endpoint = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
    
    if not project_endpoint:
        raise ValueError(
            "AZURE_AI_PROJECT_ENDPOINT environment variable is required. "
            "Set it to your Azure AI project endpoint, e.g., "
            "https://<your-account>.services.ai.azure.com/api/projects/<your-project>"
        )
    
    # Create Azure credentials
    credential = DefaultAzureCredential()
    
    # Create a factory function that will build the graph at runtime
    # The factory will receive a ToolClient when the agent first runs
    graph_factory = create_graph_factory()
    
    # tools defined in the project
    tool_connection_id = os.getenv("AZURE_AI_PROJECT_TOOL_CONNECTION_ID")
    tools = [{"type": "mcp", "project_connection_id": tool_connection_id}]

    adapter = from_langgraph(graph_factory, credentials=credential, tools=tools)

    print("Adapter created! Graph will be built on every request.")
    return adapter


async def main():  # pragma: no cover - sample entrypoint
    """Main function to run the agent."""
    adapter = await quickstart()
    
    if adapter:
        print("\nStarting agent server...")
        print("The graph factory will be called for every request that arrives.")
        await adapter.run_async()



# Build workflow and run agent
if __name__ == "__main__":
    asyncio.run(main())
