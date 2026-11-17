# Copyright (c) Microsoft. All rights reserved.

"""Location-aware chat with custom Invocations headers and input items."""

from __future__ import annotations

import os
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, cast

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from starlette.requests import Request
from typing_extensions import TypedDict

from langchain_azure_ai.agents.hosting import (
    FoundryCheckpointSaver,
    InvocationsHostServer,
)

load_dotenv()

_AZURE_AI_SCOPE = "https://ai.azure.com/.default"
_DEFAULT_LOCALE = "en-US"


class Location(TypedDict):
    label: str
    latitude: float
    longitude: float


class AssistantState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    locale: str
    location: Location


_request_locale: ContextVar[str] = ContextVar(
    "request_locale",
    default=_DEFAULT_LOCALE,
)
_request_location: ContextVar[Location | None] = ContextVar(
    "request_location",
    default=None,
)


def _parse_location(item: dict[str, Any]) -> Location:
    return cast(Location, item["location"])


def _temperature_unit(locale: str) -> Literal["celsius", "fahrenheit"]:
    region = locale.rsplit("-", maxsplit=1)[-1].upper()
    return "fahrenheit" if region in {"US", "BS", "BZ", "KY", "PW"} else "celsius"


def _message_text(item: dict[str, Any]) -> str:
    content = item.get("content")
    if isinstance(content, str):
        return content
    return "".join(
        part["text"]
        for part in cast(list[dict[str, Any]], content)
        if part.get("type") == "input_text"
    )


@tool
def get_weather(
    location: Annotated[str, "Location label supplied in the system context."],
    latitude: Annotated[float, "Location latitude supplied in the system context."],
    longitude: Annotated[
        float, "Location longitude supplied in the system context."
    ],
    unit: Annotated[
        Literal["celsius", "fahrenheit"],
        "Temperature unit supplied in the system context.",
    ],
) -> str:
    """Return deterministic fake weather for the supplied location."""
    conditions = ("sunny", "partly cloudy", "windy", "light rain")
    seed = int(abs(latitude * 10) + abs(longitude * 10))
    temperature_c = 14 + seed % 15
    if unit == "fahrenheit":
        temperature = round(temperature_c * 9 / 5 + 32)
        suffix = "F"
    else:
        temperature = temperature_c
        suffix = "C"
    condition = conditions[seed % len(conditions)]
    return f"Fake weather for {location}: {temperature} degrees {suffix}, {condition}."


@tool
def get_current_time() -> str:
    """Return the current UTC date and time."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


@tool
def calculator(
    expression: Annotated[str, "A math expression to evaluate, e.g. '42 * 17'."],
) -> str:
    """Evaluate a simple math expression and return the result."""
    try:
        return str(eval(expression, {"__builtins__": {}}))  # noqa: S307
    except Exception as exc:
        return f"Error: {exc}"


def _build_chat_model() -> ChatOpenAI:
    project_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"].rstrip("/")
    deployment = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4o")
    credential = DefaultAzureCredential()
    project = AIProjectClient(endpoint=project_endpoint, credential=credential)
    openai_client = project.get_openai_client()
    token_provider = get_bearer_token_provider(credential, _AZURE_AI_SCOPE)

    return ChatOpenAI(
        model=deployment,
        base_url=str(openai_client.base_url),
        api_key=token_provider,
        use_responses_api=True,
        output_version="responses/v1",
        # LangGraph manages message history instead of the model service.
        store=False,
    )


def _system_prompt(state: AssistantState) -> str:
    locale = state.get("locale", _DEFAULT_LOCALE)
    location = state.get("location")
    prompt = (
        "You are a concise personal assistant. Use the language and formatting "
        f"conventions associated with locale {locale}. "
    )
    if location is None:
        return (
            prompt
            + "No location has been shared. If the user asks about weather, ask "
            "them to share a location."
        )

    unit = _temperature_unit(locale)
    return (
        prompt
        + f"The user shared {location['label']} at "
        f"{location['latitude']}, {location['longitude']}. For weather questions, "
        "call get_weather with exactly this location, these coordinates, and "
        f"the {unit} unit."
    )


def _build_graph(model: ChatOpenAI):
    tools = [get_weather, get_current_time, calculator]
    tool_model = model.bind_tools(tools)

    async def assistant(state: AssistantState) -> dict[str, list[BaseMessage]]:
        response = await tool_model.ainvoke(
            [SystemMessage(content=_system_prompt(state)), *state["messages"]]
        )
        return {"messages": [response]}

    def route_after_assistant(state: AssistantState) -> str:
        latest = state["messages"][-1]
        return "tools" if isinstance(latest, AIMessage) and latest.tool_calls else END

    builder = StateGraph(AssistantState)
    builder.add_node("assistant", assistant)
    builder.add_node("tools", ToolNode(tools))
    builder.add_edge(START, "assistant")
    builder.add_conditional_edges("assistant", route_after_assistant)
    builder.add_edge("tools", "assistant")
    return builder.compile(checkpointer=FoundryCheckpointSaver())


class LocationAwareInvocationsHostServer(
    InvocationsHostServer[AssistantState, AssistantState]
):
    """Parse custom request extensions into location-aware graph state."""

    async def parse_request(self, request: Request) -> tuple[str, bool]:
        data = await request.json()
        raw_message = data.get("message")
        if isinstance(raw_message, str):
            message, stream = await super().parse_request(request)
            _request_location.set(None)
        else:
            location_item = next(
                item
                for item in raw_message
                if item.get("message_type") == "location"
            )
            user_message = next(
                item
                for item in raw_message
                if item.get("type") == "message" and item.get("role") == "user"
            )
            message = _message_text(user_message)
            stream = bool(data.get("stream", False))
            _request_location.set(_parse_location(location_item))

        _request_locale.set(
            request.headers.get("x-client-user-locale", _DEFAULT_LOCALE)
        )
        return cast(str, message), stream

    def build_input(self, message: str) -> AssistantState:
        graph_input = super().build_input(message)
        graph_input["locale"] = _request_locale.get()
        if location := _request_location.get():
            graph_input["location"] = location
        return cast(AssistantState, graph_input)


def main() -> None:
    graph = _build_graph(_build_chat_model())
    LocationAwareInvocationsHostServer(graph).run(
        port=int(os.environ.get("PORT", "8088"))
    )


if __name__ == "__main__":
    main()
