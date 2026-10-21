# Copyright (c) Microsoft. All rights reserved.

import asyncio
import json
import logging
import os
from copy import deepcopy
from dataclasses import dataclass

from azure.ai.agentserver.responses import (
    CreateResponse,
    ResponseContext,
    ResponseEventStream,
    ResponsesAgentServerHost,
    ResponsesServerOptions,
)
from azure.ai.agentserver.responses.models import get_input_expanded
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from utils.constants import LOAD_SKILL_TOOL, SESSION_TOOLS, SYSTEM_PROMPT
from utils.skills import list_skills, load_skill
from utils.toolbox import ToolboxCallResult, ToolboxClient
from utils.utils import public_tool_output, redact

load_dotenv(override=False)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
_model = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
_toolbox_name = os.getenv("TOOLBOX_NAME", "browser-automation-tools")

_credential = DefaultAzureCredential()
_project_client = AIProjectClient(endpoint=_endpoint, credential=_credential)
_responses_client = _project_client.get_openai_client().responses
_toolbox = ToolboxClient(
    f"{_endpoint.rstrip('/')}/toolboxes/{_toolbox_name}/mcp",
    _credential,
)
_tools: list[dict] | None = None


@dataclass(frozen=True)
class BrowserSessionState:
    browser_session_id: str
    live_view_url: str | None


_active_sessions: dict[str, BrowserSessionState] = {}
_last_session: str | None = None
_session_lock = asyncio.Lock()


def _get_input_text(request: CreateResponse) -> str | None:
    value = request.get("input")
    if isinstance(value, str):
        return value
    for item in get_input_expanded(request):
        content = item.get("content")
        if isinstance(content, str):
            return content
        for part in content or []:
            if text := part.get("text"):
                return text
    return None


def _build_input(current_input: str, history: list) -> list[dict]:
    input_items = []
    call_ids = {
        item["call_id"] for item in history
        if item.get("type") == "function_call"
    }
    output_ids = {
        item["call_id"] for item in history
        if item.get("type") == "function_call_output"
    }
    paired_ids = call_ids & output_ids
    for item in history:
        item_type = item.get("type")
        if item_type in ("function_call", "function_call_output"):
            call_id = item["call_id"]
            if call_id not in paired_ids:
                logger.warning("Skipping unmatched tool history item: %s", call_id)
                continue
            if item_type == "function_call":
                input_items.append({
                    "type": item_type,
                    "call_id": call_id,
                    "name": item["name"],
                    "arguments": item["arguments"],
                })
            else:
                input_items.append({
                    "type": item_type,
                    "call_id": call_id,
                    "output": item["output"],
                })
            continue
        for content in item.get("content") or []:
            text = content.get("text")
            if content.get("type") == "output_text" and text:
                input_items.append({"role": "assistant", "content": text})
            elif content.get("type") == "input_text" and text:
                input_items.append({"role": "user", "content": text})
    if _active_sessions:
        input_items.append({
            "role": "user",
            "content": (
                "[Active sessions: "
                + json.dumps({
                    name: state.browser_session_id
                    for name, state in _active_sessions.items()
                })
                + f", default: {_last_session}]"
            ),
        })
    input_items.append({"role": "user", "content": current_input})
    return input_items


def _session_info() -> dict:
    return {
        "sessions": {
            name: {"browserSessionId": state.browser_session_id, "connected": True}
            for name, state in _active_sessions.items()
        },
        "default": _last_session,
    }


def _resolve_session(reference: str | None) -> tuple[str, BrowserSessionState]:
    if reference is not None and not isinstance(reference, str):
        raise ValueError("Session name or browserSessionId must be a string.")
    name = reference or _last_session
    if name is not None and name in _active_sessions:
        return name, _active_sessions[name]
    for session_name, state in _active_sessions.items():
        if state.browser_session_id == name:
            return session_name, state
    raise ValueError(
        f"Session '{name}' not found. Available: {list(_active_sessions)}"
    )


async def _browser_tool(short_name: str) -> dict:
    tools = await asyncio.to_thread(_toolbox.response_tools)
    matches = [
        tool for tool in tools
        if tool["name"].rsplit("___", maxsplit=1)[-1] == short_name
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one discovered {short_name} tool.")
    return matches[0]


async def _create_session(
    name: str | None,
    arguments: dict | None = None,
    tool_name: str | None = None,
) -> ToolboxCallResult:
    global _last_session
    if name is None:
        number = 1
        while f"session-{number}" in _active_sessions:
            number += 1
        name = f"session-{number}"
    if not isinstance(name, str) or not name.strip() or name == "all":
        raise ValueError("A non-empty session name other than 'all' is required.")
    if name in _active_sessions:
        state = _active_sessions[name]
        return ToolboxCallResult(
            output=json.dumps({
                "status": "already_exists",
                "session": name,
                "browserSessionId": state.browser_session_id,
            }),
            browser_session_id=state.browser_session_id,
            session_name=name,
        )
    if tool_name is None:
        tool_name = (await _browser_tool("create_browser_session"))["name"]
    result = await asyncio.to_thread(
        _toolbox.call_tool, tool_name, arguments or {}
    )
    if result.is_error:
        return result
    if not result.browser_session_id:
        raise RuntimeError("Browser creation returned no browserSessionId.")
    _active_sessions[name] = BrowserSessionState(
        result.browser_session_id, result.live_view_url
    )
    _last_session = name
    result.session_name = name
    summary = {
        "status": "created",
        "session": name,
        "browserSessionId": result.browser_session_id,
        "result": result.output,
    }
    result.public_output = json.dumps({
        **summary,
        "result": result.public_output if result.public_output is not None else result.output,
    }, ensure_ascii=False)
    result.output = json.dumps(summary, ensure_ascii=False)
    return result


async def _close_session(
    reference: str | None,
    arguments: dict | None = None,
    tool_name: str | None = None,
) -> ToolboxCallResult:
    global _last_session
    name, state = _resolve_session(reference)
    tool = await _browser_tool("close_browser_session")
    tool_name = tool_name or tool["name"]
    properties = tool["parameters"].get("properties", {})
    session_parameter = next(
        key for key in ("browserSessionId", "browser_session_id")
        if key in properties
    )
    close_arguments = dict(arguments or {})
    close_arguments[session_parameter] = state.browser_session_id
    result = await asyncio.to_thread(
        _toolbox.call_tool, tool_name, close_arguments
    )
    result.session_name = name
    if not result.is_error:
        del _active_sessions[name]
        if _last_session == name:
            _last_session = next(iter(_active_sessions), None)
    return result


async def _handle_tool_call(
    call: object, used_sessions: set[str] | None = None
) -> ToolboxCallResult:
    global _last_session
    name = getattr(call, "name", "")
    arguments = json.loads(getattr(call, "arguments", "") or "{}")
    logger.info("[tool] name=%s arguments=%s", name, redact(json.dumps(arguments)))

    if name == "load_skill":
        skill_name = arguments.get("skill_name", "")
        return ToolboxCallResult(
            output=json.dumps(load_skill(skill_name), ensure_ascii=False)
        )

    async with _session_lock:
        if name == "list_sessions":
            return ToolboxCallResult(output=json.dumps(_session_info()))
        if name == "create_session":
            if not isinstance(arguments["name"], str):
                raise ValueError("Session name must be a string.")
            return await _create_session(arguments["name"])
        if name == "end_session":
            reference = arguments["name"]
            if not isinstance(reference, str) or not reference.strip():
                raise ValueError("A non-empty session name is required.")
            if reference != "all":
                return await _close_session(reference)
            results = {}
            public_results = {}
            is_error = False
            for session_name in list(_active_sessions):
                result = await _close_session(session_name)
                results[session_name] = result.output
                public_results[session_name] = (
                    result.public_output if result.public_output is not None else result.output
                )
                is_error = is_error or result.is_error
            summary = {
                "status": "close_failed" if is_error else "ended_all",
                "results": results,
                "remaining": list(_active_sessions),
            }
            return ToolboxCallResult(
                output=json.dumps(summary),
                is_error=is_error,
                public_output=json.dumps({**summary, "results": public_results}),
            )

        short_name = name.rsplit("___", maxsplit=1)[-1]
        if short_name == "create_browser_session":
            return await _create_session(None, arguments, name)
        browser_tools = await asyncio.to_thread(_toolbox.response_tools)
        tool = next(
            (tool for tool in browser_tools if tool["name"] == name), None
        )
        if tool is None:
            raise ValueError(f"Unknown browser tool: {name}")
        properties = tool["parameters"].get("properties", {})
        session_parameter = next(
            (key for key in ("browserSessionId", "browser_session_id")
             if key in properties),
            None,
        )
        if session_parameter is None:
            return await asyncio.to_thread(_toolbox.call_tool, name, arguments)

        reference = arguments.get(session_parameter)
        if reference is not None and not isinstance(reference, str):
            raise ValueError("Session name or browserSessionId must be a string.")
        created = None
        if not reference and not _active_sessions and short_name != "close_browser_session":
            created = await _create_session("default")
            if created.is_error:
                return created
        session_name, state = _resolve_session(reference)
        arguments[session_parameter] = state.browser_session_id
        if short_name == "close_browser_session":
            return await _close_session(session_name, arguments, name)

        _last_session = session_name
        if used_sessions is not None:
            used_sessions.add(session_name)
        result = await asyncio.to_thread(_toolbox.call_tool, name, arguments)
        result.session_name = session_name
        if created is not None:
            result.live_view_url = created.live_view_url
        return result


async def _get_tools() -> list[dict]:
    global _tools
    if _tools is None:
        browser_tools = await asyncio.to_thread(_toolbox.response_tools)
        browser_tools = deepcopy(browser_tools)
        for tool in browser_tools:
            parameters = tool["parameters"]
            for key in ("browserSessionId", "browser_session_id"):
                property_schema = parameters.get("properties", {}).get(key)
                if property_schema is not None:
                    property_schema["description"] = (
                        "Friendly session name or service browserSessionId. "
                        "Omit to use the default browser session."
                    )
                    parameters["required"] = [
                        required for required in parameters.get("required", [])
                        if required != key
                    ]
        _tools = [LOAD_SKILL_TOOL, *SESSION_TOOLS, *browser_tools]
    return _tools


async def _run_agent_loop(input_items: list[dict], used_sessions: set[str]):
    instructions = SYSTEM_PROMPT.format(skills=", ".join(list_skills()))
    tools = await _get_tools()

    for _ in range(20):
        response = await asyncio.to_thread(
            _responses_client.create,
            model=_model,
            instructions=instructions,
            input=input_items,
            tools=tools,
            store=False,
        )
        tool_calls = [
            item
            for item in response.output
            if getattr(item, "type", None) == "function_call"
        ]
        if not tool_calls:
            yield "reply", response.output_text or "(No response)"
            return

        for call in tool_calls:
            yield "function_call", call
            failed = True
            session_text = None
            live_view_urls = [
                state.live_view_url for state in _active_sessions.values()
                if state.live_view_url
            ]
            try:
                result = await _handle_tool_call(call, used_sessions)
                failed = result.is_error
                if result.live_view_url:
                    live_view_urls.append(result.live_view_url)
                    session_text = (
                        f"**{result.session_name or 'Browser session'}**: "
                        f"[Live View]({result.live_view_url})\n\n"
                    )
                output = result.output
                public_output = (
                    result.public_output if result.public_output is not None else output
                )
                if result.is_error:
                    output = f"Tool error: {output}"
                    public_output = f"Tool error: {public_output}"
            except Exception as exc:
                logger.exception("Tool call failed: %s", call.name)
                output = f"Tool call failed: {exc}"
                public_output = output

            input_items.append({
                "type": "function_call",
                "id": call.id,
                "call_id": call.call_id,
                "name": call.name,
                "arguments": call.arguments,
            })
            input_items.append({
                "type": "function_call_output",
                "call_id": call.call_id,
                "output": output,
            })
            yield "function_call_output", {
                "call_id": call.call_id,
                "output": public_tool_output(
                    call.name, public_output, failed, live_view_urls,
                ),
            }
            if session_text:
                yield "chat", session_text
            yield "log", f"🔧 `{call.name}`\n"

    yield "reply", "Tool-call limit reached before the task completed."


app = ResponsesAgentServerHost(
    options=ResponsesServerOptions(
        default_fetch_history_count=20,
        sse_keep_alive_interval_seconds=15,
    ),
)


@app.response_handler
async def handler(
    request: CreateResponse,
    context: ResponseContext,
    cancellation_signal: asyncio.Event,
):
    stream = ResponseEventStream(
        response_id=context.response_id,
        request=request,
    )
    yield stream.emit_created()
    yield stream.emit_in_progress()

    user_input = _get_input_text(request) or ""
    verbose_mode = user_input.strip().startswith("/verbose")
    if verbose_mode:
        user_input = user_input.replace("/verbose", "", 1).strip()

    if not user_input:
        for event in stream.output_item_message("No input provided."):
            yield event
    else:
        try:
            history = await context.get_history()
        except Exception as exc:
            logger.warning("get_history failed; continuing without history: %s", exc)
            history = []

        input_items = _build_input(user_input, history)
        used_sessions: set[str] = set()
        final_reply = ""
        async for kind, value in _run_agent_loop(input_items, used_sessions):
            if cancellation_signal.is_set():
                yield stream.emit_incomplete()
                return
            if kind == "function_call":
                for event in stream.output_item_function_call(
                    name=value.name,
                    call_id=value.call_id,
                    arguments=value.arguments if value.name == "load_skill" else "{}",
                ):
                    yield event
            elif kind == "function_call_output":
                for event in stream.output_item_function_call_output(
                    call_id=value["call_id"], output=value["output"]
                ):
                    yield event
            elif kind == "chat" or (kind == "log" and verbose_mode):
                for event in stream.output_item_message(value):
                    yield event
            elif kind == "reply":
                final_reply = value

        if cancellation_signal.is_set():
            yield stream.emit_incomplete()
            return
        for event in stream.output_item_message(final_reply):
            yield event
        links = [
            f"- **{name}**: [Live View]({state.live_view_url})"
            for name, state in _active_sessions.items()
            if state.live_view_url
        ]
        if links:
            for event in stream.output_item_message(
                "\n\n---\n\n**Active Browser Sessions:**\n\n" + "\n".join(links) + "\n"
            ):
                yield event
    yield stream.emit_completed()


app.run()
