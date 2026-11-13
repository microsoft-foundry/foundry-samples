# Copyright (c) Microsoft. All rights reserved.
"""Minimal native A2A Echo agent; no LLM or application storage wrapper."""

import logging
import os

os.environ.setdefault("OTEL_INSTRUMENTATION_A2A_SDK_ENABLED", "false")

from a2a.helpers import get_message_text, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill
from a2a.utils.errors import TaskNotCancelableError
from azure.ai.agentserver.a2a import A2AAgentServerHost
from azure.ai.agentserver.core import AgentConfig

logger = logging.getLogger("a2a.echo")


class EchoExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.message is None:
            raise ValueError("A2A request must contain a message")
        task = new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.add_artifact(
            parts=[
                new_text_part(
                    f"Echo: {get_message_text(context.message)}",
                    media_type="text/plain",
                )
            ],
        )
        await updater.complete()
        logger.info("A2A_ECHO_COMPLETED task_id=%s", task.id)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise TaskNotCancelableError(message="Echo completes within the request")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    config = AgentConfig.from_env()
    card = AgentCard(
        name="A2A Echo",
        description="Returns the supplied text with an Echo prefix in a completed A2A Task.",
        version="1.0.0",
        capabilities=AgentCapabilities(),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                protocol_version="1.0",
                url=f"http://localhost:{config.port}/a2a",
            )
        ],
        skills=[
            AgentSkill(
                id="echo",
                name="Echo",
                description="Echo text without an LLM or Toolbox.",
                tags=["echo"],
                examples=["hello"],
            )
        ],
    )
    A2AAgentServerHost(agent_card=card, agent_executor=EchoExecutor()).run(
        host="0.0.0.0" if config.is_hosted else "127.0.0.1"
    )
