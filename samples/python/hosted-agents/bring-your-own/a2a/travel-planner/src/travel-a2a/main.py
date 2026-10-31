# Copyright (c) Microsoft. All rights reserved.
"""Native A2A flight/hotel specialists and a Toolbox-only travel planner."""

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
from azure.ai.agentserver.a2a import A2AAgentServerHost
from azure.ai.agentserver.core import AgentConfig
from azure.core.exceptions import AzureError
from catalogs import FLIGHT_EXAMPLE, HOTEL_EXAMPLE, search_flights, search_hotels

logger = logging.getLogger("a2a.travel")
DESCRIPTIONS = {
    "flights": "Search a fixed synthetic round-trip flight catalog. Send a JSON query as text with these fields: "
    + json.dumps(FLIGHT_EXAMPLE),
    "hotels": "Search a fixed synthetic hotel catalog. Send a JSON query as text with these fields: "
    + json.dumps(HOTEL_EXAMPLE),
    "planner": "Plan a synthetic business trip using Flight and Hotel A2A tools in a managed Foundry Toolbox.",
}


class TravelExecutor(AgentExecutor):
    def __init__(self, role: str, planner=None) -> None:
        self.role = role
        self.planner = planner

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
            if self.role == "planner":
                result = await self.planner.plan(text)
            else:
                query = json.loads(text)
                result = (
                    search_flights(query)
                    if self.role == "flights"
                    else search_hotels(query)
                )
                result["execution_id"] = uuid4().hex
                result["task_id"] = task.id
            await updater.add_artifact(
                parts=[
                    new_text_part(
                        json.dumps(result, ensure_ascii=False), media_type="text/plain"
                    )
                ]
            )
            await updater.complete()
            logger.info("A2A_TRAVEL_COMPLETED role=%s task_id=%s", self.role, task.id)
        except (
            ValueError,
            TypeError,
            RuntimeError,
            httpx.HTTPError,
            AzureError,
        ) as error:
            logger.exception("A2A_TRAVEL_FAILED role=%s task_id=%s", self.role, task.id)
            await updater.failed(
                new_text_message(
                    f"Travel request failed in {self.role}: {error}",
                    role=Role.ROLE_AGENT,
                )
            )
            raise RuntimeError(
                f"Travel request failed in {self.role}: {error}"
            ) from error

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    role = os.environ["AGENT_ROLE"]
    if role not in DESCRIPTIONS:
        raise ValueError("AGENT_ROLE must be flights, hotels or planner")
    config = AgentConfig.from_env()
    planner = None
    if role == "planner":
        from planner import TravelPlanner

        planner = TravelPlanner(
            os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            os.environ["TOOLBOX_ENDPOINT"],
        )
    card = AgentCard(
        name={
            "flights": "Flight Agent",
            "hotels": "Hotel Agent",
            "planner": "Travel Planner",
        }[role],
        description=DESCRIPTIONS[role],
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
                id=role,
                name=role.title(),
                description=DESCRIPTIONS[role],
                tags=["synthetic-travel"],
            )
        ],
    )
    host = A2AAgentServerHost(
        agent_card=card, agent_executor=TravelExecutor(role, planner)
    )

    @host.shutdown_handler
    async def close_services() -> None:
        if planner is not None:
            await planner.close()

    host.run(host="0.0.0.0" if config.is_hosted else "127.0.0.1")


if __name__ == "__main__":
    main()
