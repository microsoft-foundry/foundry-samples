# Copyright (c) Microsoft. All rights reserved.

"""Steerable regular Agent Framework agent with a model-free smoke path."""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from typing import Annotated
from uuid import uuid4

from agent_framework import (
    Agent,
    AgentContext,
    AgentMiddleware,
    AgentResponse,
    AgentResponseUpdate,
    Content,
    Message,
    ResponseStream,
    tool,
)
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.responses import ResponsesServerOptions
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from pydantic import Field

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("steering")

STEERING_MARKER = "[STEERING-READY-731]"
STEERING_CANARY_PATTERN = re.compile(r"\[STEERING-SUCCEEDED:[A-Z0-9-]+\]")
AGENT_ID = "steering-agent"
AGENT_NAME = "steering"


@tool(approval_mode="never_require")
async def run_long_task(
    duration_seconds: Annotated[
        int,
        Field(
            description="How many seconds the simulated task should run.", ge=1, le=120
        ),
    ] = 60,
) -> str:
    """Run a finite asynchronous task long enough to admit another turn."""
    logger.info("Long-running task started for %s seconds.", duration_seconds)
    try:
        for _ in range(duration_seconds):
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        # Explicit response cancellation must release the task rather than
        # suppressing cancellation and retaining conversation resources.
        logger.info("Long-running task cancelled.")
        raise
    finally:
        logger.info("Long-running task released its resources.")

    return "[FIRST-NATURAL-COMPLETE]"


class DeterministicMarkerMiddleware(AgentMiddleware):
    """Return the smoke marker without invoking the model."""

    async def process(
        self,
        context: AgentContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        last_message = context.messages[-1] if context.messages else None
        input_text = last_message.text if last_message is not None else ""
        canary_match = STEERING_CANARY_PATTERN.search(input_text)
        marker = (
            STEERING_MARKER
            if STEERING_MARKER in input_text
            else canary_match.group(0)
            if canary_match
            else None
        )

        if marker is None:
            await call_next()
            return

        if not context.stream:
            context.result = AgentResponse(
                messages=[
                    Message(
                        role="assistant",
                        contents=[marker],
                        author_name=context.agent.name,
                        message_id=str(uuid4()),
                    )
                ],
                agent_id=context.agent.id,
            )
            return

        async def marker_updates() -> AsyncIterator[AgentResponseUpdate]:
            yield AgentResponseUpdate(
                contents=[Content.from_text(text=marker)],
                role="assistant",
                author_name=context.agent.name,
                agent_id=context.agent.id,
                message_id=str(uuid4()),
                finish_reason="stop",
            )

        def finalize(
            updates: Sequence[AgentResponseUpdate],
        ) -> AgentResponse:
            return AgentResponse.from_updates(updates)

        context.result = ResponseStream(
            marker_updates(),
            finalizer=finalize,
        )


def main() -> None:
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    agent = Agent(
        client=client,
        id=AGENT_ID,
        name=AGENT_NAME,
        description="A steerable long-running AI assistant.",
        instructions=(
            "You are a concise steerable assistant. Preserve text enclosed in "
            "square brackets exactly. When asked to start the long-running task, "
            "call run_long_task with the requested duration and report its result. "
            "Treat later input on the same conversation as steering and follow "
            "the newest instruction."
        ),
        tools=[run_long_task],
        middleware=[DeterministicMarkerMiddleware()],
        default_options={"store": False},
    )

    server = ResponsesHostServer(
        agent,
        options=ResponsesServerOptions(steerable_conversations=True),
    )
    server.run()


if __name__ == "__main__":
    main()
