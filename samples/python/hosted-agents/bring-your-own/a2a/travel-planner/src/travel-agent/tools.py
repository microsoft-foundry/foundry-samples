# Copyright (c) Microsoft. All rights reserved.
"""Small Copilot custom tools forwarding text messages through managed Toolbox."""

import json
import logging

from copilot import Tool, ToolResult
from mcp import ClientSession

logger = logging.getLogger("a2a.travel.tools")


async def discover(session: ClientSession) -> list[Tool]:
    listing = await session.list_tools()
    tools = []
    for descriptor in listing.tools:
        if (
            descriptor.meta is None
            or descriptor.meta.get("tool_configuration", {}).get("type") != "a2a"
        ):
            continue

        async def invoke(invocation, name=descriptor.name):
            try:
                arguments = invocation.arguments
                if not isinstance(arguments, dict):
                    raise TypeError("Specialist tool arguments must be a JSON object")
                message = arguments.get("message")
                if not isinstance(message, str):
                    message = json.dumps(arguments)
                result = await session.call_tool(
                    name,
                    {"message": {"parts": [{"kind": "text", "text": message}]}},
                )
                if result.isError:
                    raise RuntimeError(
                        "Toolbox specialist failed: " + result.model_dump_json()
                    )
            except Exception:
                logger.exception("Toolbox call failed: tool=%s", name)
                raise
            return ToolResult(
                result_type="success",
                text_result_for_llm=result.model_dump_json(),
            )

        tools.append(
            Tool(
                name=f"specialist_{len(tools) + 1}",
                description=descriptor.description or descriptor.name,
                parameters={
                    "type": "object",
                    "properties": {
                        "message": {
                            "type": "string",
                            "description": "Complete self-contained travel request for this specialist.",
                        }
                    },
                    "required": ["message"],
                },
                handler=invoke,
            )
        )
    if not tools:
        raise RuntimeError("Toolbox exposes no A2A specialist tools")
    return tools
