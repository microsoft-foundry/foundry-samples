# Copyright (c) Microsoft. All rights reserved.
"""Native A2A Flight Agent using Copilot SDK reasoning over dummy inventory."""

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
from catalog import FLIGHTS
from client import ask

logger = logging.getLogger("a2a.flights")
INSTRUCTIONS = """You are a synthetic Flight Agent. Use only this dummy inventory.
Interpret natural-language or JSON requests. Filter by route, departure/return dates,
arrival deadline (including timezone), seats and refundability yourself.
Calculate total USD cents as travelers * (fare_cents + tax_cents + baggage_cents).
Return every matching flight ID, arrival, refundability, price components and
calculated traveler total in readable Markdown. Explain exclusions or no match.
Do not use Python or calculator tools. Ask if essential details are missing.
Never invent inventory, live prices, bookings or payments.
Dummy inventory (all price fields are integer USD cents):
""" + json.dumps(
    FLIGHTS
)


class FlightExecutor(AgentExecutor):
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.message is None:
            raise ValueError("A2A request must contain a message")
        task = new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()
        try:
            answer = await ask(INSTRUCTIONS, get_message_text(context.message))
            await updater.add_artifact(
                parts=[new_text_part(answer, media_type="text/plain")]
            )
            await updater.complete()
        except Exception as error:
            logger.exception("Flight agent failed: task_id=%s", task.id)
            await updater.failed(
                new_text_message(f"Flight agent failed: {error}", role=Role.ROLE_AGENT)
            )
            raise

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    config = AgentConfig.from_env()
    card = AgentCard(
        name="Flight Agent",
        description="Copilot SDK flight specialist using dummy inventory.",
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
                id="flights",
                name="Flight Agent",
                description="Find and price synthetic flights from trip requirements.",
                tags=["travel", "flights"],
            )
        ],
    )
    A2AAgentServerHost(agent_card=card, agent_executor=FlightExecutor()).run(
        host="0.0.0.0" if config.is_hosted else "127.0.0.1"
    )
