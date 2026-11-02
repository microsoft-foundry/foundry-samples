# Copyright (c) Microsoft. All rights reserved.
"""Native A2A Hotel Agent; owns its catalog and never calls the planner."""

import json
import logging
import os
from uuid import uuid4

os.environ.setdefault("OTEL_INSTRUMENTATION_A2A_SDK_ENABLED", "false")

import httpx2 as httpx
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
from agent import HotelAgent
from azure.ai.agentserver.a2a import A2AAgentServerHost
from azure.ai.agentserver.core import AgentConfig
from azure.core.exceptions import AzureError
from catalog import EXAMPLE

logger = logging.getLogger("a2a.hotels")
DESCRIPTION = (
    "Use an LLM to assess raw synthetic hotels and calculate the stay. Send a JSON query as text: "
    + json.dumps(EXAMPLE)
)


class HotelExecutor(AgentExecutor):
    def __init__(self, agent: HotelAgent) -> None:
        self.agent = agent

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.message is None:
            raise ValueError("A2A request did not contain a message")
        text = get_message_text(context.message)
        if not text.strip() or len(text) > 16000:
            raise ValueError("Supply between 1 and 16000 characters")
        task = new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()
        try:
            result = await self.agent.search(json.loads(text))
            result.update(execution_id=uuid4().hex, task_id=task.id)
            await updater.add_artifact(
                parts=[new_text_part(json.dumps(result), media_type="text/plain")]
            )
            await updater.complete()
            logger.info("A2A_HOTELS_COMPLETED task_id=%s", task.id)
        except (
            ValueError,
            TypeError,
            RuntimeError,
            httpx.HTTPError,
            AzureError,
        ) as error:
            logger.exception("A2A_HOTELS_FAILED task_id=%s", task.id)
            await updater.failed(
                new_text_message(f"Hotel search failed: {error}", role=Role.ROLE_AGENT)
            )
            raise RuntimeError(f"Hotel search failed: {error}") from error

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    config = AgentConfig.from_env()
    agent = HotelAgent(
        os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
    )
    card = AgentCard(
        name="Hotel Agent",
        description=DESCRIPTION,
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
                id="hotels",
                name="Hotel Agent",
                description=DESCRIPTION,
                tags=["synthetic-travel", "hotels"],
            )
        ],
    )
    host = A2AAgentServerHost(agent_card=card, agent_executor=HotelExecutor(agent))

    @host.shutdown_handler
    async def close_services() -> None:
        await agent.close()

    host.run(host="0.0.0.0" if config.is_hosted else "127.0.0.1")


if __name__ == "__main__":
    main()
