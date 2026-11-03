# Copyright (c) Microsoft. All rights reserved.
"""Native A2A support-case agent with Copilot SDK and Foundry state storage."""

import json
import logging
import os

os.environ.setdefault("OTEL_INSTRUMENTATION_A2A_SDK_ENABLED", "false")

from a2a.helpers import (
    get_message_text,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.tasks import TaskUpdater
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, Role
from azure.ai.agentserver.a2a import A2AAgentServerHost
from azure.ai.agentserver.core import AgentConfig
from client import ask

logger = logging.getLogger("a2a.support")


class SupportExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.message is None:
            raise ValueError("A2A request must contain a message")
        task = new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()
        try:
            answer, storage = await ask(get_message_text(context.message))
            await updater.add_artifact(
                name="support-answer",
                parts=[new_text_part(answer, media_type="text/plain")],
            )
            await updater.add_artifact(
                name="state-store-operations",
                parts=[
                    new_text_part(
                        json.dumps(storage, indent=2), media_type="application/json"
                    )
                ],
            )
            await updater.complete()
        except Exception as error:
            logger.exception("Support case request failed: task_id=%s", task.id)
            await updater.failed(
                new_text_message(
                    f"Support case request failed: {error}", role=Role.ROLE_AGENT
                )
            )
            raise

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    config = AgentConfig.from_env()
    card = AgentCard(
        name="Support Case Agent",
        description="Open synthetic cases, persist findings, retrieve history and save resolution summaries.",
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
                id="support-cases",
                name="Support case workspace",
                description="Manage saved synthetic support cases across separate requests using Foundry state storage.",
                tags=["support", "state-store", "copilot"],
            )
        ],
    )
    A2AAgentServerHost(agent_card=card, agent_executor=SupportExecutor()).run(
        host="0.0.0.0" if config.is_hosted else "127.0.0.1"
    )
