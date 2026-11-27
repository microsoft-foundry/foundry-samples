# Copyright (c) Microsoft. All rights reserved.

"""Location-aware chat with custom Responses headers and input items."""

from __future__ import annotations

import os
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, cast

from azure.ai.agentserver.responses import CreateResponse, ResponseContext
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send
from typing_extensions import TypedDict

from langchain_azure_ai.agents.hosting import (
    FoundryCheckpointSaver,
    ResponsesHostServer,
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


def _parse_location(item: dict[str, Any]) -> Location:
    return cast(Location, item["location"])


def _temperature_unit(locale: str) -> Literal["celsius", "fahrenheit"]:
    region = locale.rsplit("-", maxsplit=1)[-1].upper()
    return "fahrenheit" if region in {"US", "BS", "BZ", "KY", "PW"} else "celsius"


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


class _LocaleHeaderMiddleware:
    """Expose the custom locale header while the request is handled."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        token = _request_locale.set(
            headers.get("x-client-user-locale", _DEFAULT_LOCALE)
        )
        try:
            await self._app(scope, receive, send)
        finally:
            _request_locale.reset(token)


class LocationAwareResponsesHostServer(ResponsesHostServer):
    """Parse custom request extensions into location-aware graph state."""

    def __init__(self, graph: Any) -> None:
        super().__init__(graph)
        self.app.add_middleware(_LocaleHeaderMiddleware)

    async def build_input(
        self,
        request: CreateResponse,
        context: ResponseContext,
        *,
        skip_call_ids: frozenset[str] | None = None,
    ) -> dict[str, Any]:
        input_items = await context.get_input_items()
        location_item = next(
            (
                item
                for item in input_items
                if isinstance(item, dict)
                and item.get("type") == "message"
                and item.get("message_type") == "location"
            ),
            None,
        )
        graph_input = await super().build_input(
            request,
            context,
            skip_call_ids=skip_call_ids,
        )
        graph_input["locale"] = _request_locale.get()
        if location_item is not None:
            graph_input["location"] = _parse_location(location_item)
        return graph_input


def main() -> None:
    host = LocationAwareResponsesHostServer(_build_graph(_build_chat_model()))
    host.run(port=int(os.environ.get("PORT", "8088")))


if __name__ == "__main__":
    main()
